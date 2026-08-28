"""Core background daemon orchestrating audio capture, STT, LLM interpretation, streaming dictation, and injection."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from pathlib import Path
from typing import Optional

from spic.config import SpicConfig, load_config
from spic.audio.recorder import AudioRecorder
from spic.audio.stream_recorder import StreamAudioRecorder
from spic.stt.engine import STTEngine
from spic.stt.stream_worker import StreamTranscriptionWorker
from spic.interpreter.llm_router import LLMRouter
from spic.injector.input_injector import InputInjector
from spic.shortcuts import GlobalKeyHoldListener
from spic.ui.hud import FloatingHUD

logger = logging.getLogger("spic.daemon")

DEFAULT_SOCKET_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", Path.home() / ".cache")) / "spic"
SOCKET_FILE = DEFAULT_SOCKET_DIR / "daemon.sock"


class SpicDaemon:
    """Main Spic background service supporting toggle dictation and continuous stream dictation."""

    def __init__(self, config: Optional[SpicConfig] = None):
        self.config = config or load_config()

        self.hud = FloatingHUD(self.config.ui)
        self.stt = STTEngine(self.config.stt)
        self.interpreter = LLMRouter(self.config.llm)
        self.injector = InputInjector(self.config.injection)

        # Standard toggle audio recorder
        self.recorder = AudioRecorder(
            sample_rate=self.config.audio.sample_rate,
            channels=self.config.audio.channels,
            device_index=self.config.audio.device_index,
            vad_energy_threshold=self.config.audio.vad_energy_threshold,
            silence_duration_seconds=self.config.audio.silence_duration_seconds,
            enable_noise_reduction=self.config.audio.enable_noise_reduction,
            on_level_update=self.hud.update_audio_level,
        )

        # Continuous On-the-GO Stream Worker & Recorder
        self.stream_worker = StreamTranscriptionWorker(
            stt=self.stt,
            injector=self.injector,
            sample_rate=self.config.audio.sample_rate,
            smart_spacing=self.config.stream.smart_spacing,
            on_chunk_injected=self._on_stream_chunk_injected,
            on_stream_finished=self._on_stream_finished,
        )

        self.stream_recorder = StreamAudioRecorder(
            sample_rate=self.config.audio.sample_rate,
            channels=self.config.audio.channels,
            device_index=self.config.audio.device_index,
            vad_energy_threshold=self.config.audio.vad_energy_threshold,
            chunk_pause_threshold_seconds=self.config.stream.chunk_pause_threshold_seconds,
            max_chunk_duration_seconds=self.config.stream.max_chunk_duration_seconds,
            enable_noise_reduction=self.config.audio.enable_noise_reduction,
            on_level_update=self.hud.update_audio_level,
            on_chunk_ready=self._on_stream_chunk_ready,
        )

        # Hardware global key-hold listener
        self.key_listener = GlobalKeyHoldListener(
            binding=self.config.shortcuts.hold_stream_dictation,
            on_hold_start=self.start_stream_dictation,
            on_hold_stop=self.stop_stream_dictation,
            hold_delay_ms=self.config.shortcuts.hold_trigger_delay_ms,
        )

        self._running = False
        self._current_smart_mode = False
        self._action_lock = threading.Lock()
        self._stream_active = False

    def start(self) -> None:
        """Start the background daemon, IPC socket server, hardware key listener, and HUD."""
        self._running = True
        logger.info("Starting Spic Daemon...")

        # 1. Start HUD overlay
        if self.config.ui.show_hud:
            self.hud.start()

        # 2. Warm up STT model in background
        threading.Thread(target=self._warmup_models, daemon=True).start()

        # 3. Start Global Key-Hold Listener (for Ctrl+M On-the-GO Stream Dictation)
        self.key_listener.start()

        # 4. Start IPC Socket Listener for hotkeys
        self._listen_ipc()

    def stop(self) -> None:
        """Stop daemon and all background workers."""
        self._running = False
        self.key_listener.stop()
        self.stream_recorder.stop_stream()
        self.stream_worker.stop(wait=False)
        self.hud.stop()

    def _warmup_models(self) -> None:
        """Pre-load STT model into RAM to ensure zero latency on first keypress."""
        try:
            logger.info("Pre-warming local Whisper model...")
            self.stt._get_model()
            logger.info("Whisper model ready.")
            print("\n" + "=" * 60)
            print(" ✅ SPIC DAEMON IS READY & ACTIVE")
            print("=" * 60)
            print(" Global Shortcuts Active:")
            print(f"   • {self.config.shortcuts.fast_dictation:<22} -> Fast Voice Dictation")
            print(f"   • {self.config.shortcuts.smart_copilot:<22} -> Smart Voice Copilot")
            print(f"   • HOLD {self.config.shortcuts.hold_stream_dictation:<17} -> On-the-GO Continuous Stream Dictation")
            print("=" * 60 + "\n")
        except Exception as e:
            logger.warning(f"Model warm-up warning: {e}")

    # =========================================================================
    # Continuous On-the-GO Stream Dictation Mode (Hold Hotkey)
    # =========================================================================
    def start_stream_dictation(self) -> None:
        """Begin continuous streaming dictation session."""
        with self._action_lock:
            if self._stream_active or self.recorder.is_recording:
                return

            self._stream_active = True
            logger.info("🚀 [Stream Dictation] Started continuous listening session...")

            self.hud.show_listening()
            self.stream_worker.start()

            try:
                self.stream_recorder.start_stream()
            except Exception as e:
                logger.error(f"Failed to start stream recorder: {e}")
                self._stream_active = False
                self.hud.hide()

    def stop_stream_dictation(self) -> None:
        """End continuous streaming dictation session."""
        with self._action_lock:
            if not self._stream_active:
                return

            self._stream_active = False
            logger.info("🛑 [Stream Dictation] Key released. Flushing remaining speech chunks...")

            # Transition HUD into processing wave while final in-flight chunks are injected
            self.hud.show_processing()
            self.stream_recorder.stop_stream()

    def _on_stream_chunk_ready(self, audio_np, is_final: bool) -> None:
        """Callback from StreamAudioRecorder when a speech chunk is sliced."""
        self.stream_worker.enqueue_chunk(audio_np, is_final)

    def _on_stream_chunk_injected(self, text: str) -> None:
        """Callback when an on-the-go stream chunk has been typed at cursor."""
        logger.debug(f"Stream chunk live injected: '{text}'")

    def _on_stream_finished(self, has_injected: bool = True) -> None:
        """Callback when all stream chunks have been transcribed and injected."""
        if has_injected:
            logger.info("✨ [Stream Dictation] All chunks processed and injected.")
            self.hud.show_done("✓ Injected")
        else:
            logger.info("✨ [Stream Dictation] No speech detected during hold session.")
            self.hud.hide()

    # =========================================================================
    # Standard Toggle Dictation Mode (Press & Release)
    # =========================================================================
    def toggle_listening(self, smart_mode: bool = False) -> None:
        """Toggle standard recording state."""
        with self._action_lock:
            if self._stream_active:
                return

            if not self.recorder.is_recording:
                self._start_listening_flow(smart_mode)
            else:
                self._stop_and_process_flow()

    def _start_listening_flow(self, smart_mode: bool) -> None:
        """Start listening and display waveform."""
        logger.info(f"🎙️ Listening started (Smart Mode: {smart_mode})...")
        self._current_smart_mode = smart_mode
        self.hud.show_listening()

        def _on_silence_auto_stop():
            with self._action_lock:
                if self.recorder.is_recording:
                    logger.info("Silence detected. Auto-stopping recording...")
                    self._stop_and_process_flow()

        try:
            self.recorder.start_recording(
                auto_stop_on_silence=True,
                on_silence=_on_silence_auto_stop,
            )
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.hud.hide()

    def _stop_and_process_flow(self) -> None:
        """Stop recording, transcribe, interpret, and inject."""
        logger.info("Stopping recording and beginning processing pipeline...")
        self.hud.show_processing()

        audio = self.recorder.stop_recording()
        if audio.size == 0:
            logger.info("No speech detected.")
            self.hud.hide()
            return

        def _async_pipeline():
            try:
                raw_text = self.stt.transcribe(audio, sample_rate=self.config.audio.sample_rate)
                if not raw_text:
                    logger.info("Transcription yielded empty text.")
                    self.hud.hide()
                    return

                logger.info(f"Raw Speech: '{raw_text}'")
                final_text = self.interpreter.process(raw_text, force_smart_mode=self._current_smart_mode)
                logger.info(f"Final Interpreted Text: '{final_text}'")

                if not final_text:
                    self.hud.hide()
                    return

                success, method = self.injector.inject_text(final_text)
                logger.info(f"Injection status: {success} via {method}")

                if method in ("uinput_paste", "pynput_paste", "pynput_typing"):
                    self.hud.show_done("✓ Injected")
                elif method == "copied_to_clipboard":
                    self.hud.show_done("📋 Copied (Ctrl+V)")
                else:
                    self.hud.show_done("✓ Done")

            except Exception as e:
                logger.error(f"Pipeline error: {e}", exc_info=True)
                self.hud.hide()

        threading.Thread(target=_async_pipeline, daemon=True).start()

    def _listen_ipc(self) -> None:
        """Listen on a user-restricted local Unix socket with peer UID verification."""
        DEFAULT_SOCKET_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(DEFAULT_SOCKET_DIR, 0o700)
        except Exception:
            pass

        if SOCKET_FILE.exists():
            try:
                SOCKET_FILE.unlink()
            except Exception:
                pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(SOCKET_FILE))
        try:
            os.chmod(str(SOCKET_FILE), 0o600)
        except Exception:
            pass

        server.listen(5)
        logger.info(f"IPC Socket listening securely at {SOCKET_FILE}")

        my_uid = os.getuid()

        while self._running:
            try:
                conn, _ = server.accept()

                try:
                    import struct
                    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
                    pid, uid, gid = struct.unpack("3i", creds)
                    if uid != my_uid:
                        logger.warning(f"Unauthorized IPC connection attempt from UID {uid} (expected {my_uid})")
                        conn.close()
                        continue
                except Exception:
                    pass

                data = conn.recv(1024).decode("utf-8").strip()
                if data == "TRIGGER_FAST":
                    self.toggle_listening(smart_mode=False)
                    conn.sendall(b"OK\n")
                elif data == "TRIGGER_SMART":
                    self.toggle_listening(smart_mode=True)
                    conn.sendall(b"OK\n")
                elif data == "STREAM_START":
                    self.start_stream_dictation()
                    conn.sendall(b"OK\n")
                elif data == "STREAM_STOP":
                    self.stop_stream_dictation()
                    conn.sendall(b"OK\n")
                elif data == "STOP":
                    conn.sendall(b"BYE\n")
                    conn.close()
                    break
                else:
                    conn.sendall(b"UNKNOWN\n")
                conn.close()
            except Exception as e:
                if self._running:
                    logger.error(f"IPC error: {e}")

        server.close()
