"""Native PipeWire and ALSA non-blocking audio recorder."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Callable, Optional
import numpy as np

from spic.audio.vad import VoiceActivityDetector
from spic.audio.enhancer import AudioEnhancer

logger = logging.getLogger("spic.audio.recorder")


class AudioRecorder:
    """Non-blocking, low-latency audio recorder tapping PipeWire (via pw-record/arecord/sounddevice)."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device_index: Optional[int] = None,
        vad_energy_threshold: float = 0.015,
        silence_duration_seconds: float = 1.2,
        max_duration_seconds: float = 60.0,
        enable_noise_reduction: bool = True,
        on_level_update: Optional[Callable[[float], None]] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self.silence_duration_seconds = silence_duration_seconds
        self.max_duration_seconds = max_duration_seconds
        self.enable_noise_reduction = enable_noise_reduction
        self.on_level_update = on_level_update

        self.vad = VoiceActivityDetector(energy_threshold=vad_energy_threshold, sample_rate=sample_rate)
        self.enhancer = AudioEnhancer(sample_rate=sample_rate)

        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._frames: list[np.ndarray] = []
        self._is_recording = False
        self._start_time = 0.0
        self._last_speech_time = 0.0
        self._lock = threading.Lock()
        self._silence_callback: Optional[Callable[[], None]] = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def start_recording(self, auto_stop_on_silence: bool = False, on_silence: Optional[Callable[[], None]] = None) -> None:
        """Start capturing audio via native PipeWire stream."""
        with self._lock:
            if self._is_recording:
                return

            self._frames = []
            self._is_recording = True
            self._start_time = time.time()
            self._last_speech_time = time.time()
            self._has_speech = False
            self._silence_callback = on_silence

            cmd = self._build_record_command()
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=int(self.sample_rate * 0.05 * 2 * self.channels),  # 50ms buffer
                )
                logger.debug(f"Spawned audio recording process: {' '.join(cmd)}")
            except Exception as e:
                self._is_recording = False
                logger.error(f"Failed to launch audio recorder command ({cmd}): {e}")
                raise

            # Spawn reader thread
            self._thread = threading.Thread(target=self._stream_reader_loop, daemon=True)
            self._thread.start()

    def stop_recording(self) -> np.ndarray:
        """Stop capturing and return the enhanced 16kHz float32 audio array."""
        with self._lock:
            if not self._is_recording:
                return np.array([], dtype=np.float32)

            self._is_recording = False

            if self._process is not None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=0.5)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                finally:
                    self._process = None

            if not self._frames:
                return np.array([], dtype=np.float32)

            raw_audio = np.concatenate(self._frames, axis=0).flatten()

        # Apply Voice Activity trimming
        trimmed = self.vad.trim_silence(raw_audio)

        # Apply Audio Enhancements
        if self.enable_noise_reduction and trimmed.size > 0:
            enhanced = self.enhancer.enhance(trimmed)
            return enhanced

        return trimmed

    def _build_record_command(self) -> list[str]:
        """Select best available audio recording CLI (pw-record > arecord)."""
        if shutil.which("pw-record"):
            # Native PipeWire capture streaming 16kHz s16 mono PCM to stdout
            return [
                "pw-record",
                "--rate", str(self.sample_rate),
                "--channels", str(self.channels),
                "--format", "s16",
                "--raw",
                "-",
            ]
        elif shutil.which("arecord"):
            # ALSA capture streaming raw s16le PCM to stdout
            return [
                "arecord",
                "-f", "S16_LE",
                "-r", str(self.sample_rate),
                "-c", str(self.channels),
                "-t", "raw",
                "-q",
            ]
        else:
            raise RuntimeError("Neither 'pw-record' nor 'arecord' was found on your system.")

    def _stream_reader_loop(self) -> None:
        """Read 50ms PCM chunks from subprocess stdout in real-time."""
        bytes_per_sample = 2  # 16-bit PCM = 2 bytes
        chunk_samples = int(self.sample_rate * 0.05)  # 50ms block
        chunk_bytes = chunk_samples * self.channels * bytes_per_sample
        initial_grace_seconds = 4.0  # Allow 4 seconds for user to start speaking

        proc = self._process
        if proc is None or proc.stdout is None:
            return

        while self._is_recording and proc.poll() is None:
            try:
                raw_data = proc.stdout.read(chunk_bytes)
                if not raw_data:
                    break

                # Convert raw s16le bytes to float32 normalized [-1.0, 1.0]
                int16_chunk = np.frombuffer(raw_data, dtype=np.int16)
                float32_chunk = int16_chunk.astype(np.float32) / 32768.0

                with self._lock:
                    self._frames.append(float32_chunk)

                # Compute RMS & update HUD
                rms = self.vad.compute_rms(float32_chunk)
                if self.on_level_update is not None:
                    try:
                        self.on_level_update(rms)
                    except Exception:
                        pass

                # Check max duration safety limit (60s)
                now = time.time()
                if now - self._start_time >= self.max_duration_seconds:
                    logger.info("Max recording duration reached (60s). Auto-stopping...")
                    if self._silence_callback is not None:
                        cb = self._silence_callback
                        self._silence_callback = None
                        threading.Thread(target=cb, daemon=True).start()
                    break

                # VAD & Intelligent Silence Tracking
                is_curr_speech = self.vad.is_speech(float32_chunk)
                if is_curr_speech:
                    self._has_speech = True
                    self._last_speech_time = now
                else:
                    if self._has_speech:
                        # User spoke and is now silent
                        silence_duration = now - self._last_speech_time
                        if (
                            self._silence_callback is not None
                            and silence_duration >= self.silence_duration_seconds
                        ):
                            logger.info(f"Silence detected ({silence_duration:.1f}s). Auto-stopping...")
                            cb = self._silence_callback
                            self._silence_callback = None
                            threading.Thread(target=cb, daemon=True).start()
                    else:
                        # User hasn't started speaking yet - check initial grace period
                        if (
                            self._silence_callback is not None
                            and (now - self._start_time) >= initial_grace_seconds
                        ):
                            logger.info("No speech detected during initial grace period. Auto-stopping...")
                            cb = self._silence_callback
                            self._silence_callback = None
                            threading.Thread(target=cb, daemon=True).start()

            except Exception as e:
                logger.warning(f"Error in stream reader loop: {e}")
                break
