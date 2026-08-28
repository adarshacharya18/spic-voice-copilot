# 🔧 Spic Troubleshooting Guide

This guide covers common issues and solutions when running Spic on Linux desktop environments.

---

## 1. Text is Copied to Clipboard but Not Automatically Pasted

### Cause:
On Ubuntu and modern Wayland desktops, background applications are prohibited from simulating key events (`pynput` / XWayland) into native Wayland windows (e.g. VS Code, Chrome, Terminal) for security.

### Solution:
Grant user permissions to the Linux Kernel **`/dev/uinput`** virtual hardware subsystem:

```bash
# Run the persistent permission setup script
./scripts/setup_uinput.sh
```

Verify with the built-in injection test:
```bash
python3 -m spic.cli test-injection
```

---

## 2. "VS Code is Not Responding" or Window Freezes on Paste

### Cause:
Earlier versions of clipboard injection claimed ownership of the Wayland selection without servicing event requests, causing Electron to block.

### Solution:
Ensure you are running the latest version of Spic. Spic now prioritizes **Direct Kernel Hardware-Level Typing (`uinput_typing`)**, which types directly through kernel keycodes without touching the Wayland clipboard bus.

---

## 3. Top-Left Dropdown Appears or Screenshot Opens When Holding Hotkey

### Cause:
Holding modifier keys (like `Right Alt` or `Super + Alt`) while Spic injects characters causes the Linux window manager to combine the keys:
- **`Alt + Space`**: Opens the GNOME Window Titlebar Context Menu (whose first option is *"Take a Screenshot"*).
- **`Super + Alt + S`**: Triggers the GNOME Orca Screen Reader audio toggle.
- **`Super + H`**: Minimizes the focused window.

### Solution:
Use a dedicated non-modifier key for hold stream dictation:
- **`RightControl`** (Default): Set `"hold_stream_dictation": "<RightControl>"` in `~/.config/spic/config.json`.
- **`F8` or `F9`**: Set `"hold_stream_dictation": "<F8>"` (isolated along top function row).
- **Toggle Mode**: Use `Ctrl + Alt + Space` for hands-free dictation without holding any key.

---

## 4. Accidental Key Taps Trigger the Microphone / HUD

### Cause:
Bumping or briefly pressing the hold key triggers a micro-recording.

### Solution:
Spic includes a **Hold Intent Activation Timer** (default: `500ms`). Quick taps under 500ms are completely cancelled with zero mic or HUD activity. You can adjust this in `~/.config/spic/config.json`:
```json
{
  "shortcuts": {
    "hold_trigger_delay_ms": 500
  }
}
```

---

## 5. Local STT Permissions (`/dev/input/event*` Access)

### Cause:
Global hardware key holding requires read permissions to `/dev/input/event*` devices.

### Solution:
Ensure your Linux user belongs to the `input` group:
```bash
sudo usermod -aG input "$USER"
```
*(Log out and log back in for group membership to take effect).*

---

## 6. Microphone Error: `'NoneType' object has no attribute 'InputStream'`

### Cause:
The legacy `sounddevice` / `PortAudio` library was missing system shared libraries (`libportaudio2`).

### Solution:
Spic now uses native **PipeWire** audio streaming (`pw-record`). Verify your microphone with:
```bash
python3 -m spic.cli test-mic
```

---

## 7. LLM Request Times Out (`Read timed out (read timeout=30)`)

### Cause:
Running large reasoning models (like 8B parameter models) on a laptop CPU can take 30–60+ seconds.

### Solution:
1. Use **Fast Dictation Mode** (`Ctrl + Alt + Space`) or **On-the-GO Stream Dictation** (Hold `RightControl`) — both execute voice self-corrections instantly with zero LLM overhead.
2. For Smart Copilot mode, use the optimized **`llama3.2:3b`** model:
   ```bash
   ollama pull llama3.2:3b
   ```
3. Or use an instant cloud provider like **Groq** (`export GROQ_API_KEY="..."`), which returns results in <250ms.
