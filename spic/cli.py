"""Command-line interface for Spic Voice Copilot."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import time
from pathlib import Path

# Ensure root repository directory is in sys.path when directly invoked by desktop shortcuts
_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from spic.config import CONFIG_FILE, load_config, save_config
from spic.daemon import SOCKET_FILE, SpicDaemon
from spic.shortcuts import register_gnome_shortcuts
from spic.interpreter.rule_cleaner import RuleCleaner
from spic.interpreter.llm_router import LLMRouter


def send_ipc_trigger(smart: bool = False) -> bool:
    """Send trigger command to running daemon socket."""
    if not SOCKET_FILE.exists():
        print("[Spic] Daemon is not currently running. Start it with: python -m spic.cli start")
        return False

    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(SOCKET_FILE))
        msg = b"TRIGGER_SMART\n" if smart else b"TRIGGER_FAST\n"
        client.sendall(msg)
        response = client.recv(1024).decode("utf-8").strip()
        client.close()
        return response == "OK"
    except Exception as e:
        print(f"[Spic] Failed to communicate with daemon: {e}")
        return False


def cmd_start(args) -> None:
    """Run the Spic background daemon."""
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 60)
    print(" 🎙️  Spic: Native Ubuntu Voice Copilot")
    print("=" * 60)
    print(f"Config: {CONFIG_FILE}")
    print("Listening for hotkeys and triggers...")
    print("Press Ctrl+C to stop.\n")

    daemon = SpicDaemon()
    try:
        daemon.start()
    except KeyboardInterrupt:
        print("\nStopping Spic daemon...")


def cmd_trigger(args) -> None:
    """Trigger the daemon to toggle listening."""
    success = send_ipc_trigger(smart=args.smart)
    if not success:
        sys.exit(1)


def cmd_test_mic(args) -> None:
    """Test microphone capture and display live audio volume."""
    from spic.audio.recorder import AudioRecorder

    print("[Spic] Testing microphone capture on PipeWire for 5 seconds...")
    print("Speak into your microphone to verify levels:")

    def _meter(rms):
        bars = int(rms * 100)
        sys.stdout.write(f"\rVolume: [{'#' * min(40, bars):<40}] (RMS: {rms:.4f})")
        sys.stdout.flush()

    recorder = AudioRecorder(on_level_update=_meter)
    try:
        recorder.start_recording()
        time.sleep(5)
        audio = recorder.stop_recording()
        print(f"\n\nCaptured {len(audio)} audio samples ({len(audio)/16000:.2f}s). Mic test successful!")
    except Exception as e:
        print(f"\n[Spic] Mic test error: {e}")


def cmd_test_stt(args) -> None:
    """Test STT recording and transcription."""
    from spic.audio.recorder import AudioRecorder
    from spic.stt.engine import STTEngine

    config = load_config()
    stt = STTEngine(config.stt)
    recorder = AudioRecorder()

    print("[Spic] Speak for 4 seconds...")
    recorder.start_recording()
    for i in range(4, 0, -1):
        print(f"Recording... {i}s remaining")
        time.sleep(1)

    audio = recorder.stop_recording()
    print("Transcribing with local Whisper model...")
    text = stt.transcribe(audio)
    print(f"\n✅ Result: \"{text}\"")


def cmd_test_llm(args) -> None:
    """Test LLM interpreter with mock text."""
    config = load_config()
    router = LLMRouter(config.llm)

    sample_input = args.input or "Hello, I wanted to schedule a meeting on Monday scratch that on Tuesday morning at 10 AM um period"
    print(f"Testing Provider: {config.llm.provider} (Model: {config.llm.model})")
    print(f"Input:  \"{sample_input}\"")

    print("\n1. Rule Cleaner Output:")
    print(f"   -> \"{router.rule_cleaner.clean(sample_input)}\"")

    print("\n2. Smart LLM Output:")
    try:
        smart_output = router.process(sample_input, force_smart_mode=True)
        print(f"   -> \"{smart_output}\"")
    except Exception as e:
        print(f"   -> Error: {e}")


def cmd_test_rules(args) -> None:
    """Test rule-based command cleaner on various spoken phrases."""
    cleaner = RuleCleaner()
    test_cases = [
        ("Um hello this is a test comma how are you question mark", "Hello this is a test, how are you?"),
        ("Send the invoice to Bob scratch that send it to Alice", "Send it to Alice"),
        ("Please add a new line and then write thank you period", "Please add a\nand then write thank you."),
        ("Delete this statement", ""),
    ]

    print("[Spic] Running Rule Cleaner Test Suite:\n")
    for raw, expected in test_cases:
        res = cleaner.clean(raw)
        print(f"Input:    \"{raw}\"")
        print(f"Output:   \"{res}\"")
        print(f"Expected: \"{expected}\"\n")


def cmd_test_injection(args) -> None:
    """Test injecting text into the active window after a short countdown."""
    from spic.injector.input_injector import InputInjector

    config = load_config()
    injector = InputInjector(config.injection)
    sample_text = args.text or "✨ Hello from Spic Voice Copilot!"

    print("[Spic] Testing text injection into active cursor location.")
    if injector._uinput is not None:
        print("  -> Linux /dev/uinput virtual keyboard is ACTIVE.")
    else:
        print("  -> /dev/uinput not configured. Using clipboard + paste simulation.")
        print("     (To enable direct hardware-level typing across all Wayland apps, run: ./scripts/setup_uinput.sh)")

    print("\nSwitch focus to any text editor or input field now:")
    for i in range(3, 0, -1):
        print(f"Injecting in {i}...")
        time.sleep(1)

    print(f"Injecting: \"{sample_text}\"")
    success, method = injector.inject_text(sample_text)
    if success:
        print(f"✅ Injection completed via method: '{method}'!")
    else:
        print("❌ Injection failed.")


def cmd_setup_shortcuts(args) -> None:
    """Register GNOME desktop shortcuts."""
    python_bin = sys.executable
    spic_entry = str(Path(__file__).resolve())
    register_gnome_shortcuts(python_bin, spic_entry)


def cmd_config(args) -> None:
    """Display current config."""
    config = load_config()
    print(config.model_dump_json(indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Spic: The Native Linux Voice Copilot")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start
    p_start = subparsers.add_parser("start", help="Start the Spic background daemon")
    p_start.set_defaults(func=cmd_start)

    # trigger
    p_trig = subparsers.add_parser("trigger", help="Send trigger signal to running daemon")
    p_trig.add_argument("--smart", action="store_true", help="Trigger in smart LLM interpretation mode")
    p_trig.set_defaults(func=cmd_trigger)

    # test-mic
    p_mic = subparsers.add_parser("test-mic", help="Test microphone capture & volume")
    p_mic.set_defaults(func=cmd_test_mic)

    # test-stt
    p_stt = subparsers.add_parser("test-stt", help="Record and test Speech-to-Text")
    p_stt.set_defaults(func=cmd_test_stt)

    # test-llm
    p_llm = subparsers.add_parser("test-llm", help="Test LLM interpretation")
    p_llm.add_argument("--input", type=str, default=None, help="Custom input text to test")
    p_llm.set_defaults(func=cmd_test_llm)

    # test-rules
    p_rules = subparsers.add_parser("test-rules", help="Test rule-based command cleaner")
    p_rules.set_defaults(func=cmd_test_rules)

    # test-injection
    p_inj = subparsers.add_parser("test-injection", help="Test text injection into active window")
    p_inj.add_argument("--text", type=str, default=None, help="Text to inject")
    p_inj.set_defaults(func=cmd_test_injection)

    # setup-shortcuts
    p_sc = subparsers.add_parser("setup-shortcuts", help="Register GNOME system shortcuts")
    p_sc.set_defaults(func=cmd_setup_shortcuts)

    # config
    p_cfg = subparsers.add_parser("config", help="Display configuration")
    p_cfg.set_defaults(func=cmd_config)

    parsed = parser.parse_args()
    parsed.func(parsed)


if __name__ == "__main__":
    main()
