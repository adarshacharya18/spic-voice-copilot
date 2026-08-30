"""Command-line interface for Spic Voice Copilot."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import time
from pathlib import Path

# Force X11 backend for GDK on Wayland so window coordinates (top-middle) are respected
os.environ["GDK_BACKEND"] = "x11"
if "/usr/lib/python3/dist-packages" not in sys.path:
    sys.path.append("/usr/lib/python3/dist-packages")

try:
    import gi
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk
    Gdk.set_allowed_backends("x11")
except Exception:
    pass

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


def send_ipc_stream_trigger(start: bool = True) -> bool:
    """Send stream start or stop command to running daemon socket."""
    if not SOCKET_FILE.exists():
        print("[Spic] Daemon is not currently running. Start it with: python -m spic.cli start")
        return False

    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(SOCKET_FILE))
        msg = b"STREAM_START\n" if start else b"STREAM_STOP\n"
        client.sendall(msg)
        response = client.recv(1024).decode("utf-8").strip()
        client.close()
        return response == "OK"
    except Exception as e:
        print(f"[Spic] Failed to communicate with daemon: {e}")
        return False


def cmd_trigger_stream(args) -> None:
    """Trigger the daemon stream dictation mode (start/stop)."""
    start_mode = not args.stop
    action = "START" if start_mode else "STOP"
    print(f"[Spic] Sending STREAM_{action} to daemon...")
    success = send_ipc_stream_trigger(start=start_mode)
    if not success:
        sys.exit(1)


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
    """Record speech and run a side-by-side comparison benchmark of Local Whisper vs Google Gemini Live STT."""
    from spic.audio.recorder import AudioRecorder
    from spic.stt.engine import STTEngine
    from spic.stt.gemini_live import GeminiLiveSTT
    from spic.config import STTConfig

    config = load_config()
    recorder = AudioRecorder()
    duration = getattr(args, "duration", 4) or 4

    print("\n" + "=" * 65)
    print(" 🎙️  Spic Speech-to-Text Benchmark: Whisper vs. Gemini Live")
    print("=" * 65)
    print(f"Speak into your microphone for {duration} seconds...")
    recorder.start_recording()
    for i in range(duration, 0, -1):
        print(f" 🔴 Recording... {i}s remaining")
        time.sleep(1)

    audio = recorder.stop_recording()
    duration_s = len(audio) / 16000
    print(f"\nCaptured {len(audio)} audio samples ({duration_s:.2f}s).\n")

    # 1. Test Local Whisper
    whisper_cfg = STTConfig(engine="faster-whisper", model_size=config.stt.model_size)
    whisper_engine = STTEngine(whisper_cfg)
    print("⏳ [1/2] Transcribing with Local Whisper (faster-whisper CPU int8)...")
    t0 = time.time()
    try:
        whisper_text = whisper_engine.transcribe(audio)
        whisper_time = time.time() - t0
        print(f"  • Latency: {whisper_time:.3f}s | Mode: 100% Offline")
        print(f"  • Output:  \"{whisper_text}\"\n")
    except Exception as e:
        whisper_text = f"Error: {e}"
        whisper_time = 0.0
        print(f"  • Failed: {e}\n")

    # 2. Test Google Gemini Live STT
    gemini_live = GeminiLiveSTT()
    print("⏳ [2/2] Transcribing with Google Gemini Live (gemini-3.5-transcribe-live)...")
    t0 = time.time()
    try:
        gemini_text = gemini_live.transcribe(audio)
        gemini_time = time.time() - t0
        if gemini_text:
            print(f"  • Latency: {gemini_time:.3f}s | Mode: Google Cloud Live WebSocket")
            print(f"  • Output:  \"{gemini_text}\"\n")
        else:
            gemini_text = "(No transcript returned / missing API key)"
            print("  • Gemini Live STT returned no text (check API key or network).\n")
    except Exception as e:
        gemini_text = f"Error: {e}"
        gemini_time = 0.0
        print(f"  • Failed: {e}\n")

    # Side-by-side summary table
    print("=" * 65)
    print(" 📊 Side-by-Side Comparison Summary")
    print("=" * 65)
    print(f" ⚡ Local Whisper:  \"{whisper_text}\" ({whisper_time:.2f}s)")
    print(f" ☁️  Gemini Live:   \"{gemini_text}\" ({gemini_time:.2f}s)")
    print("=" * 65 + "\n")


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


def cmd_test_ui(args) -> None:
    """Test floating HUD wave animations and transitions interactively."""
    import math
    from spic.ui.hud import FloatingHUD

    config = load_config()
    hud = FloatingHUD(config.ui)

    print("\n============================================================")
    print(" 🎨 Spic Floating HUD Animation Test")
    print("============================================================")
    print("Launching floating wave HUD...")
    hud.start()
    time.sleep(0.3)

    print("1. [Entering & Listening] Crimson & Coral Audio Reactive Waves (3.5s)...")
    hud.show_listening()
    for i in range(30):
        simulated_rms = 0.05 + abs(math.sin(i * 0.35)) * 0.5
        hud.update_audio_level(simulated_rms)
        time.sleep(0.12)

    print("2. [Processing / Thinking] Electric Cyan & Violet Flow Ribbon (2.5s)...")
    hud.show_processing()
    time.sleep(2.5)

    print("3. [Done & Settling] Emerald Green Pulse & Upward Exit Glide (1.5s)...")
    hud.show_done()
    time.sleep(1.5)

    hud.stop()
    print("✅ Animation cycle completed successfully!\n")


def cmd_setup_shortcuts(args) -> None:
    """Configure and register GNOME global shortcuts with conflict detection."""
    from spic.shortcuts import (
        check_shortcut_conflict,
        format_binding_label,
        get_free_recommended_shortcuts,
        normalize_binding,
        register_gnome_shortcuts,
    )

    config = load_config()
    python_bin = sys.executable
    spic_entry = str(Path(__file__).resolve())

    # 1. Flag: List Free Hotkeys
    if getattr(args, "list_free", False):
        print("\n============================================================")
        print(" 🔍 Free & Available Hotkeys on Your Desktop")
        print("============================================================")
        free_keys = get_free_recommended_shortcuts()
        if not free_keys:
            print("  No default candidate hotkeys are currently free.")
        else:
            for b, label, desc in free_keys:
                print(f"  ✅ {label:24} ({b})\n     └─ {desc}")
        print("============================================================\n")
        return

    # 2. Flag: Check specific shortcut conflict
    if getattr(args, "check", None):
        target = args.check
        norm = normalize_binding(target)
        label = format_binding_label(norm)
        conflict = check_shortcut_conflict(norm)
        print(f"\nChecking shortcut: '{target}' -> {norm} ({label})")
        if conflict:
            print(f"❌ CONFLICT: Currently assigned to:")
            print(f"   Action: {conflict['action_name']}")
            print(f"   Schema: {conflict['schema']}:{conflict['key']}")
        else:
            print(f"✅ AVAILABLE: '{label}' is completely unassigned and safe to use!\n")
        return

    # 3. Direct Flag Override (--fast / --smart)
    if getattr(args, "fast", None) or getattr(args, "smart", None):
        fast_b = normalize_binding(args.fast) if args.fast else config.shortcuts.fast_dictation
        smart_b = normalize_binding(args.smart) if args.smart else config.shortcuts.smart_copilot

        # Check conflicts
        if args.fast:
            conflict = check_shortcut_conflict(fast_b)
            if conflict and not getattr(args, "force", False):
                print(f"\n⚠️  WARNING: Fast shortcut '{fast_b}' conflicts with:")
                print(f"   Action: {conflict['action_name']} ({conflict['schema']})")
                print("   Use --force to override this shortcut.")
                return

        if args.smart:
            conflict = check_shortcut_conflict(smart_b)
            if conflict and not getattr(args, "force", False):
                print(f"\n⚠️  WARNING: Smart shortcut '{smart_b}' conflicts with:")
                print(f"   Action: {conflict['action_name']} ({conflict['schema']})")
                print("   Use --force to override this shortcut.")
                return

        config.shortcuts.fast_dictation = fast_b
        config.shortcuts.smart_copilot = smart_b
        save_config(config)
        register_gnome_shortcuts(python_bin, spic_entry, fast_b, smart_b)
        print(f"✅ Configured Shortcuts:\n  - Fast:  {format_binding_label(fast_b)} ({fast_b})\n  - Smart: {format_binding_label(smart_b)} ({smart_b})")
        return

    # 4. Interactive Wizard
    print("\n============================================================")
    print(" ⌨️  Spic Custom Hotkey Configuration Wizard")
    print("============================================================")
    curr_fast = config.shortcuts.fast_dictation
    curr_smart = config.shortcuts.smart_copilot
    print(f"Current Bindings:")
    print(f"  1. Fast Dictation (<300ms):  {format_binding_label(curr_fast)} ({curr_fast})")
    print(f"  2. Smart Copilot (LLM):      {format_binding_label(curr_smart)} ({curr_smart})\n")

    print("Recommended Free Hotkeys on your desktop:")
    free_candidates = get_free_recommended_shortcuts()
    for i, (b, label, desc) in enumerate(free_candidates[:5], start=1):
        print(f"  [{i}] {label:22} ({desc})")

    print("\nPress ENTER to keep existing bindings, or configure new ones.")

    # Prompt Fast Hotkey
    print("-" * 60)
    user_fast = input(f"Enter Fast Dictation shortcut [Default: {curr_fast}]: ").strip()
    selected_fast = curr_fast
    if user_fast:
        norm_fast = normalize_binding(user_fast)
        conflict = check_shortcut_conflict(norm_fast)
        if conflict:
            print(f"\n⚠️  WARNING: '{user_fast}' is currently in use by:")
            print(f"   Action: {conflict['action_name']}")
            print(f"   Schema: {conflict['schema']}:{conflict['key']}")
            confirm = input("   Do you want to override this system action? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                print("   Keeping existing binding.")
            else:
                selected_fast = norm_fast
        else:
            print(f"   ✅ '{format_binding_label(norm_fast)}' is free and available!")
            selected_fast = norm_fast

    # Prompt Smart Hotkey
    print("-" * 60)
    user_smart = input(f"Enter Smart Copilot shortcut [Default: {curr_smart}]: ").strip()
    selected_smart = curr_smart
    if user_smart:
        norm_smart = normalize_binding(user_smart)
        conflict = check_shortcut_conflict(norm_smart)
        if conflict:
            print(f"\n⚠️  WARNING: '{user_smart}' is currently in use by:")
            print(f"   Action: {conflict['action_name']}")
            print(f"   Schema: {conflict['schema']}:{conflict['key']}")
            confirm = input("   Do you want to override this system action? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                print("   Keeping existing binding.")
            else:
                selected_smart = norm_smart
        else:
            print(f"   ✅ '{format_binding_label(norm_smart)}' is free and available!")
            selected_smart = norm_smart

    # Save & Register
    config.shortcuts.fast_dictation = selected_fast
    config.shortcuts.smart_copilot = selected_smart
    save_config(config)

    print("\nRegistering shortcuts in GNOME desktop...")
    ok = register_gnome_shortcuts(python_bin, spic_entry, selected_fast, selected_smart)
    if ok:
        print("============================================================")
        print(" 🎉 Shortcuts Successfully Configured!")
        print(f"  • Fast Dictation: {format_binding_label(selected_fast)} ({selected_fast})")
        print(f"  • Smart Copilot:  {format_binding_label(selected_smart)} ({selected_smart})")
        print("============================================================\n")
    else:
        print("❌ Failed to register shortcuts in GNOME settings.\n")


def cmd_test_stream(args) -> None:
    """Test continuous On-the-GO stream dictation standalone with live live transcription and injection."""
    from spic.audio.stream_recorder import StreamAudioRecorder
    from spic.stt.engine import STTEngine
    from spic.stt.stream_worker import StreamTranscriptionWorker
    from spic.injector.input_injector import InputInjector

    config = load_config()
    stt = STTEngine(config.stt)
    injector = InputInjector(config.injection)

    duration = args.duration if hasattr(args, "duration") and args.duration else 10

    print("\n" + "=" * 60)
    print(" ⚡ Spic On-the-GO Stream Dictation Live Test")
    print("=" * 60)
    print(f"Starting continuous stream for {duration} seconds...")
    print("Speak freely into your microphone with natural pauses.")
    print("Each sentence will be transcribed and injected on the fly!\n")

    def _on_injected(text):
        print(f"\n  👉 [Live Chunk Injected]: \"{text}\"")

    worker = StreamTranscriptionWorker(
        stt=stt,
        injector=injector,
        smart_spacing=config.stream.smart_spacing,
        on_chunk_injected=_on_injected,
    )
    worker.start()

    recorder = StreamAudioRecorder(
        sample_rate=config.audio.sample_rate,
        chunk_pause_threshold_seconds=config.stream.chunk_pause_threshold_seconds,
        max_chunk_duration_seconds=config.stream.max_chunk_duration_seconds,
        on_chunk_ready=worker.enqueue_chunk,
    )

    try:
        recorder.start_stream()
        for i in range(duration, 0, -1):
            sys.stdout.write(f"\r🎙️ Listening continuously... ({i}s remaining) ")
            sys.stdout.flush()
            time.sleep(1)
        print("\n\nStopping stream and finalizing remaining audio...")
        recorder.stop_stream()
        worker.stop(wait=True)
        print("✅ Stream session test finished!\n")
    except KeyboardInterrupt:
        print("\nInterrupted. Finalizing stream...")
        recorder.stop_stream()
        worker.stop(wait=True)


def cmd_memory(args) -> None:
    """Manage cross-agent persistent memory."""
    from spic.memory import AgentMemoryCoordinator, MemoryType, MemoryQuery

    coord = AgentMemoryCoordinator()

    if args.add:
        mem_type = MemoryType(args.type) if args.type else MemoryType.SEMANTIC
        ns = args.namespace or ("user_profile" if mem_type == MemoryType.SEMANTIC else "general")
        mem = coord.remember_fact(
            content=args.add,
            agent_id=args.agent or "global",
            namespace=ns,
            key=args.key,
            importance=args.importance,
        )
        print(f"✅ Stored {mem_type.value} memory (ID: {mem.id}) in namespace '{ns}':")
        print(f"   \"{mem.content}\"")

    elif args.search:
        results = coord.store.search(MemoryQuery(
            query=args.search,
            agent_id=args.agent,
            limit=args.limit or 5,
        ))
        print(f"\n🔍 Memory Search Results for '{args.search}' ({len(results)} found):")
        print("=" * 60)
        for i, res in enumerate(results, 1):
            mem = res.memory
            print(f"[{i}] Score: {res.score:.2f} | Type: {mem.memory_type.value} | Namespace: {mem.namespace}")
            print(f"    Content: \"{mem.content}\"")
            if mem.metadata:
                print(f"    Metadata: {mem.metadata}")
            print("-" * 60)
        print()

    elif args.prune:
        count = coord.decay_engine.decay_and_prune()
        print(f"🧹 Pruned and archived {count} stale memory items.")

    else:
        # Default: list memories
        items = coord.store.list_all(agent_id=args.agent, limit=args.limit or 20)
        print(f"\n🧠 Stored Agent Memories ({len(items)} items):")
        print("=" * 60)
        for i, mem in enumerate(items, 1):
            print(f"[{i}] ID: {mem.id[:8]}... | Type: {mem.memory_type.value:<10} | Namespace: {mem.namespace:<14} | Agent: {mem.agent_id}")
            print(f"    \"{mem.content}\"")
            print(f"    Accessed: {mem.last_accessed_at.strftime('%Y-%m-%d %H:%M')} (Count: {mem.access_count}) | Importance: {mem.importance}")
            print("-" * 60)
        print()


def cmd_autostart(args) -> None:
    """Manage systemd user service for background daemon autostart on PC boot."""
    systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
    service_file = systemd_user_dir / "spic.service"

    python_bin = sys.executable
    work_dir = _ROOT_DIR

    if args.enable:
        print("⚙️ Setting up systemd user service for Spic...")
        systemd_user_dir.mkdir(parents=True, exist_ok=True)

        service_content = f"""[Unit]
Description=Spic Linux Voice Copilot Background Daemon
Documentation=https://github.com/adarshacharya18/spic-voice-copilot
After=graphical-session.target pipewire.service wireplumber.service
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={python_bin} -m spic.daemon
WorkingDirectory={work_dir}
Restart=on-failure
RestartSec=3s
Environment=PYTHONUNBUFFERED=1
Environment=GDK_BACKEND=x11

[Install]
WantedBy=graphical-session.target
"""
        service_file.write_text(service_content, encoding="utf-8")
        os.chmod(str(service_file), 0o644)
        print(f"✓ Created service unit: {service_file}")

        try:
            import subprocess
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", "spic.service"], check=True)
            subprocess.run(["systemctl", "--user", "restart", "spic.service"], check=True)
            print("\n🚀 Spic daemon enabled and started automatically on PC boot!")
            print("To view status: python3 -m spic.cli autostart --status")
            print("To view live logs: python3 -m spic.cli autostart --logs")
        except Exception as e:
            print(f"❌ Failed to enable systemd service: {e}")

    elif args.disable:
        print("🛑 Disabling Spic systemd user service...")
        try:
            import subprocess
            subprocess.run(["systemctl", "--user", "stop", "spic.service"], check=False)
            subprocess.run(["systemctl", "--user", "disable", "spic.service"], check=False)
            if service_file.exists():
                service_file.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            print("✓ Spic autostart disabled.")
        except Exception as e:
            print(f"❌ Failed to disable service: {e}")

    elif args.logs:
        import subprocess
        try:
            subprocess.run(["journalctl", "--user", "-u", "spic.service", "-n", str(args.lines or 50), "--no-pager"])
        except Exception as e:
            print(f"Error fetching logs: {e}")

    else:
        # Default: show status
        import subprocess
        try:
            subprocess.run(["systemctl", "--user", "status", "spic.service"])
        except Exception as e:
            print(f"Error checking status: {e}")


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

    # trigger-stream
    p_trig_st = subparsers.add_parser("trigger-stream", help="Trigger stream dictation start/stop on running daemon")
    p_trig_st.add_argument("--start", action="store_true", default=True, help="Start stream dictation (default)")
    p_trig_st.add_argument("--stop", action="store_true", help="Stop stream dictation")
    p_trig_st.set_defaults(func=cmd_trigger_stream)

    # test-stream
    p_tstream = subparsers.add_parser("test-stream", help="Test continuous on-the-go stream dictation live")
    p_tstream.add_argument("--duration", type=int, default=10, help="Test stream duration in seconds (default: 10)")
    p_tstream.set_defaults(func=cmd_test_stream)

    # autostart (alias: service)
    for auto_cmd in ("autostart", "service"):
        p_auto = subparsers.add_parser(auto_cmd, help="Manage systemd user service for background daemon autostart on boot")
        p_auto.add_argument("--enable", action="store_true", help="Enable & start Spic daemon automatically on PC boot")
        p_auto.add_argument("--disable", action="store_true", help="Disable Spic daemon autostart")
        p_auto.add_argument("--status", action="store_true", help="Check live systemd service status")
        p_auto.add_argument("--logs", action="store_true", help="View live background logs")
        p_auto.add_argument("--lines", type=int, default=50, help="Number of log lines to show (default: 50)")
        p_auto.set_defaults(func=cmd_autostart)

    # memory
    p_mem = subparsers.add_parser("memory", help="Manage cross-agent persistent memory (CoALA framework)")
    p_mem.add_argument("--add", type=str, default=None, help="Add a new memory fact")
    p_mem.add_argument("--search", type=str, default=None, help="Search memories by query")
    p_mem.add_argument("--type", type=str, choices=["semantic", "episodic", "procedural", "working"], default="semantic", help="Memory type")
    p_mem.add_argument("--namespace", type=str, default=None, help="Memory namespace")
    p_mem.add_argument("--key", type=str, default=None, help="Optional unique key for superseding")
    p_mem.add_argument("--agent", type=str, default=None, help="Agent ID (default: global)")
    p_mem.add_argument("--importance", type=float, default=0.7, help="Importance weight (0.0 - 1.0)")
    p_mem.add_argument("--limit", type=int, default=20, help="Max results to display")
    p_mem.add_argument("--prune", action="store_true", help="Prune and archive stale low-utility memories")
    p_mem.set_defaults(func=cmd_memory)

    # test-mic
    p_mic = subparsers.add_parser("test-mic", help="Test microphone capture & volume")
    p_mic.set_defaults(func=cmd_test_mic)

    # test-stt
    p_stt = subparsers.add_parser("test-stt", help="Record speech and run a side-by-side comparison of Whisper vs Gemini Live STT")
    p_stt.add_argument("--duration", type=int, default=4, help="Recording duration in seconds (default: 4)")
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

    # test-ui (alias: test-hud)
    for ui_cmd in ("test-ui", "test-hud"):
        p_ui = subparsers.add_parser(ui_cmd, help="Test floating wave HUD animations")
        p_ui.set_defaults(func=cmd_test_ui)

    # setup-shortcuts (alias: shortcuts)
    for cmd_name in ("setup-shortcuts", "shortcuts"):
        p_sc = subparsers.add_parser(cmd_name, help="Configure & guide GNOME global hotkeys")
        p_sc.add_argument("--fast", type=str, default=None, help="Custom shortcut for Fast Dictation (e.g. 'ctrl+alt+m')")
        p_sc.add_argument("--smart", type=str, default=None, help="Custom shortcut for Smart Copilot (e.g. 'ctrl+super+k')")
        p_sc.add_argument("--list-free", action="store_true", help="List free & available hotkeys on your desktop")
        p_sc.add_argument("--check", type=str, default=None, help="Check if a specific shortcut has conflicts")
        p_sc.add_argument("--force", action="store_true", help="Override conflicting system shortcuts without confirmation")
        p_sc.set_defaults(func=cmd_setup_shortcuts)

    # config
    p_cfg = subparsers.add_parser("config", help="Display configuration")
    p_cfg.set_defaults(func=cmd_config)

    parsed = parser.parse_args()
    parsed.func(parsed)


if __name__ == "__main__":
    main()
