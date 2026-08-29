# 🔧 Spic Troubleshooting & FAQ Guide

This guide covers common issues, diagnostic steps, and solutions when running Spic on Linux desktop environments (**Ubuntu, Debian, Fedora, Arch Linux**).

---

## 1. Text is Copied to Clipboard but Not Automatically Typed

### Cause:
On modern Wayland desktops (GNOME Wayland, Sway, Hyprland), background applications are prohibited from simulating key events (`pynput` / XWayland) into native Wayland windows (e.g. VS Code, Chrome, Terminal) for security.

### Solution:
Grant user permissions to the Linux Kernel **`/dev/uinput`** virtual hardware subsystem:

```bash
# Run the persistent permission setup script
./scripts/setup_uinput.sh
```

Verify with the built-in injection test:
```bash
python3 -m spic.cli test-injection --text "✨ Spic Hardware Injection Working!"
```
*(If prompted, log out of your desktop and log back in for `input` group permissions to take effect).*

---

## 2. Spic Does Not Stop When I Move the Mouse or Press a Key

### Cause:
Spic's `ActivityTerminationWatcher` directly monitors raw hardware input streams (`/dev/input/event*`) at the Linux kernel level. If your Linux user does not have permission to read `/dev/input/event*`, the hardware watcher cannot detect your mouse or key gestures.

### Solution:
Add your user to the `input` group:
```bash
sudo usermod -aG input "$USER"
```
Then **log out of your desktop and log back in** (or restart).

---

## 3. Spic Cuts Off My Sentence While I Am Thinking

### Cause:
Earlier versions had a 1.0-second silence cutoff. In natural human speech, thinking pauses often last 1.5–2.5 seconds.

### Solution:
Spic defaults to a **5.0-second silence fallback** (`silence_duration_seconds: 5.0`).
- You have a full 5-second window to pause, think, and breathe mid-speech without being cut off.
- When you are ready to finish, simply **tap any key (e.g. `Space`, `Enter`) or nudge your mouse** for an instant $0\text{ms}$ finish!

You can adjust this anytime in `~/.config/spic/config.json`:
```json
{
  "audio": {
    "silence_duration_seconds": 5.0
  }
}
```

---

## 4. Background Service Management (`systemd --user`)

### Check Service Status:
```bash
python3 -m spic.cli autostart --status
# or: systemctl --user status spic.service
```

### View Live Daemon Logs:
```bash
python3 -m spic.cli autostart --logs
# or: journalctl --user -u spic.service -f
```

### Restart Service:
```bash
systemctl --user restart spic.service
```

### Disable Autostart:
```bash
python3 -m spic.cli autostart --disable
```

---

## 5. Microphone Audio Capture Error

### Diagnostic:
Test your microphone and audio levels:
```bash
python3 -m spic.cli test-mic
```

### Solution:
Spic uses native **PipeWire** audio capture (`pw-record`). Ensure PipeWire audio utilities are installed:
- **Ubuntu/Debian:** `sudo apt install pipewire pipewire-audio-client-libraries`
- **Fedora:** `sudo dnf install pipewire pipewire-utils`
- **Arch Linux:** `sudo pacman -S pipewire pipewire-audio`

---

## 6. Local LLM Request Times Out (Smart Copilot)

### Cause:
Running large models (like 8B or 13B models) on CPU can be slow.

### Solution:
Use the recommended fast, lightweight **3B model**:
```bash
ollama pull llama3.2:3b
```
Ensure `~/.config/spic/config.json` is set to:
```json
{
  "llm": {
    "provider": "ollama",
    "model": "llama3.2:3b",
    "base_url": "http://localhost:11434"
  }
}
```
*(For instant <250ms smart interpretation, you can also use Groq by setting `"provider": "groq"` and `export GROQ_API_KEY="gsk_..."`)*.
