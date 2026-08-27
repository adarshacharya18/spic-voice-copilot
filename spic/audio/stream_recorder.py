"""Continuous PipeWire / ALSA stream audio recorder with real-time VAD chunk slicing."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from typing import Callable, Optional
import numpy as np

from spic.audio.vad import VoiceActivityDetector
from spic.audio.enhancer import AudioEnhancer

logger = logging.getLogger("spic.audio.stream_recorder")


class StreamAudioRecorder:
    """Non-blocking audio recorder that continuously captures audio and slices speech chunks on natural pauses."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device_index: Optional[int] = None,
        vad_energy_threshold: float = 0.015,
        chunk_pause_threshold_seconds: float = 0.45,
        max_chunk_duration_seconds: float = 8.0,
        enable_noise_reduction: bool = True,
        on_level_update: Optional[Callable[[float], None]] = None,
        on_chunk_ready: Optional[Callable[[np.ndarray, bool], None]] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self.vad_energy_threshold = vad_energy_threshold
        self.chunk_pause_threshold_seconds = chunk_pause_threshold_seconds
        self.max_chunk_duration_seconds = max_chunk_duration_seconds
        self.enable_noise_reduction = enable_noise_reduction
        self.on_level_update = on_level_update
        self.on_chunk_ready = on_chunk_ready

        self.vad = VoiceActivityDetector(energy_threshold=vad_energy_threshold, sample_rate=sample_rate)
        self.enhancer = AudioEnhancer(sample_rate=sample_rate)

        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._is_streaming = False
        self._lock = threading.Lock()

        # Rolling frame accumulator for active speech chunk
        self._current_chunk_frames: list[np.ndarray] = []
        self._is_in_speech = False
        self._speech_start_time = 0.0
        self._last_speech_time = 0.0

    @property
    def is_streaming(self) -> bool:
        return self._is_streaming

    def start_stream(self) -> None:
        """Start continuous audio capture stream."""
        with self._lock:
            if self._is_streaming:
                return

            self._current_chunk_frames = []
            self._is_in_speech = False
            self._speech_start_time = 0.0
            self._last_speech_time = 0.0
            self._is_streaming = True

            cmd = self._build_record_command()
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=int(self.sample_rate * 0.05 * 2 * self.channels),  # 50ms buffer
                )
                logger.debug(f"Spawned continuous stream process: {' '.join(cmd)}")
            except Exception as e:
                self._is_streaming = False
                logger.error(f"Failed to start stream audio process: {e}")
                raise

            self._thread = threading.Thread(target=self._stream_capture_loop, daemon=True)
            self._thread.start()

    def stop_stream(self) -> None:
        """Stop capturing and flush any remaining audio as final chunk."""
        with self._lock:
            if not self._is_streaming:
                return

            self._is_streaming = False
            proc = self._process
            self._process = None
            remaining_frames = list(self._current_chunk_frames)
            self._current_chunk_frames = []

        # Terminate capture subprocess outside lock to prevent blocking
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=0.2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        # Flush final remaining audio chunk
        if remaining_frames:
            raw_audio = np.concatenate(remaining_frames, axis=0).flatten()
            trimmed = self.vad.trim_silence(raw_audio)
            if self.enable_noise_reduction and trimmed.size > 0:
                trimmed = self.enhancer.enhance(trimmed)

            if trimmed.size > int(self.sample_rate * 0.15):  # At least 150ms of audio
                if self.on_chunk_ready:
                    self.on_chunk_ready(trimmed, True)
                return

        # Emit empty final marker so consumer knows stream has concluded
        if self.on_chunk_ready:
            self.on_chunk_ready(np.array([], dtype=np.float32), True)

    def _build_record_command(self) -> list[str]:
        """Select best available audio recording CLI (pw-record > arecord)."""
        if shutil.which("pw-record"):
            return [
                "pw-record",
                "--rate", str(self.sample_rate),
                "--channels", str(self.channels),
                "--format", "s16",
                "--raw",
                "-",
            ]
        elif shutil.which("arecord"):
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

    def _stream_capture_loop(self) -> None:
        """Read 50ms PCM chunks continuously and slice speech on natural pauses."""
        bytes_per_sample = 2
        chunk_samples = int(self.sample_rate * 0.05)  # 50ms block
        chunk_bytes = chunk_samples * self.channels * bytes_per_sample

        proc = self._process
        if proc is None or proc.stdout is None:
            return

        while self._is_streaming and proc.poll() is None:
            try:
                raw_bytes = proc.stdout.read(chunk_bytes)
                if not raw_bytes or len(raw_bytes) < chunk_bytes:
                    break

                # Convert to float32 [-1.0, 1.0]
                samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                if self.channels > 1:
                    samples = samples.reshape(-1, self.channels).mean(axis=1)

                now = time.time()
                rms = self.vad.compute_rms(samples)
                is_speech = self.vad.is_speech(samples)

                # Send RMS level update to HUD visualizer
                if self.on_level_update:
                    try:
                        self.on_level_update(rms)
                    except Exception:
                        pass

                chunk_to_emit: Optional[np.ndarray] = None

                with self._lock:
                    if not self._is_streaming:
                        break

                    if is_speech:
                        if not self._is_in_speech:
                            self._is_in_speech = True
                            self._speech_start_time = now

                        self._last_speech_time = now
                        self._current_chunk_frames.append(samples)

                        # Check if max chunk duration exceeded (force slice)
                        if (now - self._speech_start_time) >= self.max_chunk_duration_seconds:
                            if self._current_chunk_frames:
                                raw_chunk = np.concatenate(self._current_chunk_frames, axis=0).flatten()
                                self._current_chunk_frames = []
                                self._is_in_speech = False
                                chunk_to_emit = raw_chunk

                    else:
                        # In silence / pause
                        if self._is_in_speech:
                            self._current_chunk_frames.append(samples)
                            silence_elapsed = now - self._last_speech_time

                            # Natural pause boundary detected!
                            if silence_elapsed >= self.chunk_pause_threshold_seconds:
                                if self._current_chunk_frames:
                                    raw_chunk = np.concatenate(self._current_chunk_frames, axis=0).flatten()
                                    self._current_chunk_frames = []
                                    self._is_in_speech = False
                                    chunk_to_emit = raw_chunk

                # Emit extracted speech slice outside lock
                if chunk_to_emit is not None and chunk_to_emit.size > int(self.sample_rate * 0.2):
                    trimmed = self.vad.trim_silence(chunk_to_emit)
                    if self.enable_noise_reduction and trimmed.size > 0:
                        trimmed = self.enhancer.enhance(trimmed)

                    if trimmed.size > int(self.sample_rate * 0.15):
                        if self.on_chunk_ready:
                            self.on_chunk_ready(trimmed, False)

            except Exception as e:
                logger.error(f"Error in stream audio loop: {e}")
                break
