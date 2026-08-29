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
from spic.stt.engine import STTEngine
from spic.interpreter.llm_router import LLMRouter
from spic.injector.input_injector import InputInjector
from spic.shortcuts import ActivityTerminationWatcher
from spic.ui.hud import FloatingHUD

logger = logging.getLogger("spic.daemon")

DEFAULT_SOCKET_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", Path.home() / ".cache")) / "spic"
SOCKET_FILE = DEFAULT_SOCKET_DIR / "daemon.sock"


class SpicDaemon:
    """Main Spic background service supporting Fast Dictation and Smart Voice Copilot."""

    def __init__(self, config: Optional[SpicConfig] = None):
        self.config = config or load_config()

        self.hud = FloatingHUD(self.config.ui)
        self.stt = STTEngine(self.config.stt)
        self.interpreter = LLMRouter(self.config.llm)
        self.injector = InputInjector(self.config.injection)

        # Standard audio recorder with dynamic VAD
        self.recorder = AudioRecorder(
            sample_rate=self.config.audio.sample_rate,
            channels=self.config.audio.channels,
            device_index=self.config.audio.device_index,
            vad_energy_threshold=self.config.audio.vad_energy_threshold,
            silence_duration_seconds=self.config.audio.silence_duration_seconds,
            enable_noise_reduction=self.config.audio.enable_noise_reduction,
            on_level_update=self.hud.update_audio_level,
        )

        # Tap-to-Start, Action-to-Finish watcher
        self.activity_watcher = ActivityTerminationWatcher(
            on_activity=self._on_user_activity_detected,
            grace_period_seconds=self.config.shortcuts.activity_termination_grace_seconds,
            mouse_threshold_px=self.config.shortcuts.mouse_move_threshold_px,
        )

        self._running = False
        self._current_smart_mode = False
        self._action_lock = threading.Lock()

    def start(self) -> None:
        """Start the background daemon, IPC socket server, and HUD."""
        self._running = True
        logger.info("Starting Spic Daemon...")

        # 1. Start HUD overlay
        if self.config.ui.show_hud:
            self.hud.start()

        # 2. Warm up STT model in background
        threading.Thread(target=self._warmup_models, daemon=True).start()

        # 3. Start IPC Socket Listener for hotkeys
        self._listen_ipc()

    def stop(self) -> None:
        """Stop daemon and all background listeners."""
        self._running = False
        self.activity_watcher.stop()
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
            print(" Global Shortcuts Active (Tap-to-Start, Action-to-Finish):")
            print(f"   • {self.config.shortcuts.fast_dictation:<24} -> Fast Voice Dictation")
            print(f"   • {self.config.shortcuts.smart_copilot:<24} -> Smart Voice Copilot")
            print(" Tip: Tap shortcut once to speak. Stops on speech pause, any key press, or mouse move!")
            print("=" * 60 + "\n")
        except Exception as e:
            logger.warning(f"Model warm-up warning: {e}")

    def _on_user_activity_detected(self) -> None:
        """Callback when user touches any key or moves/clicks mouse while recording."""
        with self._action_lock:
            if self.recorder.is_recording:
                logger.info("⚡ User action detected. Auto-stopping recording...")
                self._stop_and_process_flow()

    # =========================================================================
    # Voice Dictation Flow (Fast & Smart Modes)
    # =========================================================================
    def toggle_listening(self, smart_mode: bool = False) -> None:
        """Toggle recording state."""
        with self._action_lock:
            if not self.recorder.is_recording:
                self._start_listening_flow(smart_mode)
            else:
                self._stop_and_process_flow()

    def _start_listening_flow(self, smart_mode: bool) -> None:
        """Start listening, display HUD waveform, and activate action-to-finish watcher."""
        logger.info(f"🎙️ Listening started (Smart Mode: {smart_mode})...")
        self._current_smart_mode = smart_mode
        self.hud.show_listening()

        def _on_silence_auto_stop():
            with self._action_lock:
                if self.recorder.is_recording:
                    logger.info("Silence detected. Auto-stopping recording...")
                    self._stop_and_process_flow()

        try:
            # Activate user interaction sensor
            self.activity_watcher.start()

            self.recorder.start_recording(
                auto_stop_on_silence=True,
                on_silence=_on_silence_auto_stop,
            )
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.activity_watcher.stop()
            self.hud.hide()

    def _stop_and_process_flow(self) -> None:
        """Stop recording, deactivate sensor, transcribe, interpret, and inject."""
        self.activity_watcher.stop()
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

                if method in ("uinput_typing", "uinput_paste", "pynput_paste", "pynput_typing"):
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


def main() -> None:
    """Standalone entrypoint for spic.daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%H:%M:%S",
    )
    config = load_config()
    daemon = SpicDaemon(config)
    daemon.start()


if __name__ == "__main__":
    main()
