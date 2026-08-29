# 🐧 Spic Linux Installation & Setup Guide

This guide provides step-by-step instructions for installing and running Spic natively on Linux desktop distributions (**Ubuntu, Debian, Fedora, Arch Linux**, etc.) on both **Wayland** and **X11**.

---

## 📋 System Requirements

- **Operating System:** Linux (Kernel 5.15+)
- **Desktop Environment:** GNOME (Wayland/X11), KDE Plasma, Hyprland, Sway, or XFCE
- **Audio Server:** PipeWire (Default on modern Ubuntu, Fedora, Arch) or ALSA/PulseAudio
- **Python:** Python 3.10, 3.11, 3.12, or 3.13
- **Hardware:** 4-Core CPU + 4GB RAM (Whisper runs on CPU with `int8` quantization)

---

## 🚀 Step-by-Step Installation

### Step 1: Install System Dependencies

Install Python development libraries and PipeWire audio utilities:

#### Ubuntu / Debian:
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip pipewire pipewire-audio-client-libraries
```

#### Fedora:
```bash
sudo dnf install -y python3-pip pipewire pipewire-utils
```

#### Arch Linux / Manjaro:
```bash
sudo pacman -S python-pip pipewire pipewire-audio
```

---

### Step 2: Clone Repository & Set Up Virtual Environment

```bash
# 1. Clone repository
git clone https://github.com/adarshacharya18/spic-voice-copilot.git
cd spic-voice-copilot

# 2. Create isolated Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt
```

---

### Step 3: Configure Linux Kernel Hardware Typing Permissions

Spic uses Linux Kernel `/dev/uinput` to type directly into your active window at hardware level, bypassing Wayland window isolation.

Run the automatic permissions setup script:
```bash
./scripts/setup_uinput.sh
```

#### What this script does:
1. Creates a persistent udev rule at `/etc/udev/rules.d/99-uinput.rules`:
   ```udev
   KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"
   ```
2. Adds your Linux user to the `input` user group (`sudo usermod -aG input $USER`).
3. Reloads udev kernel rules.

> [!IMPORTANT]
> If this is your first time adding your user to the `input` group, **log out of your Linux desktop and log back in** (or reboot) for group permissions to take effect.

---

### Step 4: Register Desktop Shortcuts

Spic includes an interactive conflict-detection engine that registers native GNOME desktop hotkeys:

```bash
source .venv/bin/activate
python3 -m spic.cli setup-shortcuts
```

This registers the default hotkeys:
- **`Ctrl + Alt + Space`**: **Fast Voice Dictation** (<300ms)
- **`Ctrl + Super + Space`**: **Smart Voice Copilot** (Deep reasoning + few-shot self-corrections)

#### For Non-GNOME Desktops (KDE Plasma, Hyprland, i3):
Bind your preferred keys to execute these commands in your window manager config:
- Fast Dictation trigger: `/path/to/spic-voice-copilot/.venv/bin/python3 -m spic.cli trigger`
- Smart Copilot trigger: `/path/to/spic-voice-copilot/.venv/bin/python3 -m spic.cli trigger --smart`

---

### Step 5: Run Spic (Choose Your Mode)

Spic gives you complete control over how it runs on your system:

#### 🧪 Option A: Test in Foreground (Inspect & Audit First)
If you want to test Spic first without modifying your system startup:
```bash
# Start in foreground with live console logs
./scripts/run_daemon.sh
# or: python3 -m spic.cli start
```
- **100% Transparent:** You will see model loading, mic activity, and text injection logs in real-time.
- **Zero Persistence:** Press `Ctrl + C` at any time to instantly kill the daemon. Nothing is added to system startup.

#### 🚀 Option B: Enable Background Autostart (Once You Trust It)
Once you've tested Spic and want it to launch automatically whenever your computer boots:
```bash
# Enable user systemd service
python3 -m spic.cli autostart --enable

# Check service status
python3 -m spic.cli autostart --status
```
*(To disable autostart at any time, simply run `python3 -m spic.cli autostart --disable`).*

---

## 🧠 Optional: Local AI Model Setup (For Smart Copilot)

For Smart Copilot mode, Spic uses local SLMs (Small Language Models) via **Ollama** with zero cloud dependencies:

1. **Install Ollama** (if not already installed):
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```
2. **Download the recommended model (`llama3.2:3b`)**:
   ```bash
   ollama pull llama3.2:3b
   ```

*(Alternatively, you can configure cloud providers like Groq, Google Gemini, OpenAI, or Claude in `~/.config/spic/config.json`)*.

---

## 🧪 Self-Test Diagnostic Suite

Verify your installation with Spic's built-in self-tests:

```bash
# 1. Test microphone levels and PipeWire audio stream
python3 -m spic.cli test-mic

# 2. Test local Whisper Speech-to-Text inference
python3 -m spic.cli test-stt

# 3. Test hardware keystroke injection into focused window
python3 -m spic.cli test-injection --text "✨ Spic Hardware Injection Working!"

# 4. Test smart LLM self-correction reasoning
python3 -m spic.cli test-llm --input "select screenshot in the left drawer from the drawer"
```

---

## ⌨️ How to Use Spic

Spic uses the **"Tap-to-Start, Action-to-Finish"** interaction pattern:

1. Focus any text box or application (VS Code, Terminal, Browser, Slack, Discord).
2. **Tap `Ctrl + Alt + Space` ONCE** (or `Ctrl + Super + Space` for Smart mode) and let go immediately.
3. The floating wave HUD will illuminate. Speak your thoughts naturally.
4. **Finish instantly:**
   - Press **any key** (e.g. `Space`, `Enter`, or start typing)
   - Or **nudge your mouse** ($>15\text{px}$)
   - Or pause speaking for 1 second
5. Spic instantly stops recording and types your text at the cursor!

---

## 🛠️ Service Management Commands

```bash
# Check service status
python3 -m spic.cli autostart --status

# View live daemon logs
python3 -m spic.cli autostart --logs

# Disable autostart
python3 -m spic.cli autostart --disable

# Re-enable autostart
python3 -m spic.cli autostart --enable
```
