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
*(Or grant temporary permissions: `sudo chmod 666 /dev/uinput`)*.

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

## 3. Microphone Error: `'NoneType' object has no attribute 'InputStream'`

### Cause:
The legacy `sounddevice` / `PortAudio` library was missing system shared libraries (`libportaudio2`).

### Solution:
Spic now uses native **PipeWire** audio streaming (`pw-record`). Verify your microphone with:
```bash
python3 -m spic.cli test-mic
```

---

## 4. LLM Request Times Out (`Read timed out (read timeout=30)`)

### Cause:
Running large reasoning models (like 8B parameter models) on a laptop CPU can take 30–60+ seconds.

### Solution:
1. Use **Fast Dictation Mode** (`Ctrl + Alt + Space`) — it uses zero LLM resources and executes voice self-corrections instantly.
2. For Smart Copilot mode, use the optimized **`llama3.2:3b`** model:
   ```bash
   ollama pull llama3.2:3b
   ```
3. Or use an instant cloud provider like **Groq** (`export GROQ_API_KEY="..."`), which returns results in <250ms.

---

## 5. GNOME Desktop Shortcuts Not Triggering

### Cause:
GNOME custom keybinding settings were overwritten or not registered.

### Solution:
Re-register system shortcuts via the CLI:
```bash
python3 -m spic.cli setup-shortcuts
```
This binds:
- **`Ctrl + Alt + Space`**: Fast Voice Dictation (<300ms)
- **`Ctrl + Super + Space`**: Smart Voice Copilot
