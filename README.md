<div align="center">

# 🎙️ Spic
### *The Native, Privacy-First Voice Copilot for Linux (Wayland & X11)*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux%20%28Wayland%20%26%20X11%29-orange.svg)](https://ubuntu.com)
[![PipeWire Native](https://img.shields.io/badge/Audio-PipeWire%20Native-blueviolet.svg)](https://pipewire.org/)
[![Local AI](https://img.shields.io/badge/AI-100%25%20Local%20%26%20Private-brightgreen.svg)](https://ollama.com)

**Speak anywhere. Type everywhere.**  
Spic is a lightweight background daemon that brings a fluid, continuous voice experience natively to Linux desktops with zero cloud dependencies, on-the-go stream dictation, cognitive multi-agent memory, and kernel-level hardware typing.

---

</div>

## ✨ Key Features

- 🚀 **On-the-GO Continuous Stream Dictation:** Hold hotkey to speak continuously. Natural pauses (450ms) are sliced, transcribed asynchronously, and typed live at your cursor with smart inter-chunk spacing.
- ⏱️ **500ms Hold Intent Timer:** Accidental taps (<500ms) are completely ignored with zero mic or HUD flickering.
- 🧠 **CoALA Multi-Agent Cognitive Memory:** 4-tier persistent memory (Semantic, Episodic, Procedural, Working) with SQLite + FTS5 full-text search, dynamic exponential temporal decay, and hybrid utility scoring.
- 🔒 **100% Local & Private:** Runs completely on your machine via CPU-quantized Whisper (`faster-whisper` `int8`) and local Ollama SLMs (`llama3.2:3b`). Zero audio is sent over the internet.
- 🪄 **Few-Shot Conversational Self-Corrections:** Automatically replaces conversational corrections and phrase retries (*"select screenshot in the left drawer from the drawer"* $\to$ *"Select screenshot from the drawer"*).
- ⌨️ **Native Wayland & X11 Support:** Uses Linux Kernel `/dev/uinput` virtual hardware keyboards to bypass Wayland window isolation, allowing seamless typing in VS Code, Terminal, Chrome, Slack, Discord, and LibreOffice.
- 🎨 **Ambient Translucent Wave HUD:** Minimalist floating overlay with physics-based spring drop transitions, reactive harmonic voice ribbons, and zero distracting text.
- 🌐 **Pluggable Cloud LLM Support:** Header-authenticated cloud API support (Groq at 500+ tok/s, Google Gemini, OpenAI, Claude, OpenRouter).
- 🛡️ **Hardened Linux Security:** Enforces `0700`/`0600` file permissions, Unix domain socket peer credential verification (`SO_PEERCRED`), and ANSI escape sequence sanitization.

---

## 🌊 Visual Interface & Wave States

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 🎤 LISTENING WAVE (Audio Reactive Harmonic Ribbon)       │
│    Colors: Crimson Glow (#FF3B30) & Coral Sunset            │
│    Behavior: 3-layer composite sine splines dynamically     │
│    scale in real-time with your voice amplitude.            │
├─────────────────────────────────────────────────────────────┤
│ 2. 🧠 THINKING WAVE (Quantum Intelligence Flow)             │
│    Colors: Electric Cyan (#00F2FE) & Neon Violet            │
│    Behavior: Dual-traveling modulated wave ribbon           │
│    shimmering at 60 FPS while the model interprets.         │
├─────────────────────────────────────────────────────────────┤
│ 3. ✨ DONE WAVE (Harmonic Settle & Glow)                    │
│    Colors: Emerald Green (#10B981) & Mint Glow              │
│    Behavior: Calming harmonic wave that smoothly flattens   │
│    and glides upward out of view with spring physics.       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quickstart (3 Steps)

### 1. Clone and Install
```bash
git clone https://github.com/adarshacharya18/spic-voice-copilot.git
cd spic-voice-copilot

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Linux Hardware Typing
```bash
./scripts/setup_uinput.sh
```

### 3. Start Spic & Register Hotkeys
```bash
# Register GNOME system hotkeys
python3 -m spic.cli setup-shortcuts

# Start background daemon
./scripts/run_daemon.sh
```

---

## ⌨️ Hotkeys & Dictation Modes

| Default Hotkey | Mode | Behavior | Description |
|---|---|---|---|
| **Hold `RightControl`** | **On-the-GO Stream** | `Live on Pauses` | Hold for >500ms to speak continuously. Audio is sliced on natural pauses and typed live at your cursor. |
| **`Ctrl + Alt + Space`** | **Fast Dictation** | `<300ms` | Toggle voice typing with verbal punctuation (*"period"*, *"comma"*, *"new line"*) and instant deletions (*"scratch that"*). |
| **`Ctrl + Super + Space`** | **Smart Copilot** | `~2-3s` | Deep LLM interpretation using local `llama3.2:3b` or Cloud APIs with few-shot conversational self-corrections. |

### Customize Your Shortcuts:
```bash
# 1. Interactive configuration wizard with conflict detection
python3 -m spic.cli shortcuts

# 2. View all free & available hotkeys on your desktop
python3 -m spic.cli shortcuts --list-free

# 3. Check if a specific shortcut has system conflicts
python3 -m spic.cli shortcuts --check "ctrl+alt+m"
```

---

## 🧠 Cognitive Memory CLI

```bash
# Store user preference or fact
python3 -m spic.cli memory --add "I prefer PyTorch and Python for ML code" --type semantic --key "ml_pref" --importance 0.9

# Search memory
python3 -m spic.cli memory --search "machine learning preferences"

# Prune old / stale memories
python3 -m spic.cli memory --prune --max-age-days 90
```

---

## 🧪 CLI Diagnostics & Tools

```bash
# Test continuous stream dictation pipeline
python3 -m spic.cli test-stream

# Test microphone levels via PipeWire
python3 -m spic.cli test-mic

# Test local Speech-to-Text inference
python3 -m spic.cli test-stt

# Test self-correction & rule cleaner
python3 -m spic.cli test-rules

# Test smart LLM interpretation with few-shot prompt
python3 -m spic.cli test-llm --input "select screenshot in the left drawer from the drawer"

# Test hardware text injection into active window
python3 -m spic.cli test-injection --text "✨ Spic Hardware Injection Working!"
```

---

## ⚙️ Configuration

Spic is configured via `~/.config/spic/config.json`:

```json
{
  "stt": {
    "engine": "faster-whisper",
    "model_size": "base.en",
    "device": "cpu",
    "compute_type": "int8"
  },
  "llm": {
    "provider": "ollama",
    "model": "llama3.2:3b",
    "base_url": "http://localhost:11434"
  },
  "stream": {
    "chunk_pause_threshold_seconds": 0.45,
    "max_chunk_duration_seconds": 8.0,
    "smart_spacing": true
  },
  "shortcuts": {
    "fast_dictation": "<Control><Alt>space",
    "smart_copilot": "<Control><Super>space",
    "hold_stream_dictation": "<RightControl>",
    "hold_trigger_delay_ms": 500
  }
}
```

*For complete configuration options, see the [Configuration Guide](docs/configuration.md).*

---

## 🏛️ System Architecture

```mermaid
flowchart LR
    Mic["🎤 Microphone"] -->|PipeWire PCM| VAD["VAD Pause Slicer (450ms)"]
    VAD --> STT["Whisper Base int8"]
    STT --> Router{"Interpreter Router"}
    Router -->|Fast Stream| Spacing["Smart Inter-Chunk Spacing"]
    Router -->|Smart Mode| LLM["Few-Shot LLM + CoALA Memory"]
    Spacing --> Injector["Universal Injector"]
    LLM --> Injector
    Injector -->|Hardware Keystrokes| UInput["Kernel /dev/uinput Device"]
    UInput --> App["Focused Active Window"]
```

*For in-depth architectural details and sequence flows, see [docs/architecture.md](docs/architecture.md).*

---

## 📚 Documentation Index

- [Technical Architecture & Design](docs/architecture.md)
- [CoALA Cognitive Memory Architecture](docs/memory.md)
- [Configuration Reference](docs/configuration.md)
- [Troubleshooting & FAQ](docs/troubleshooting.md)
- [Security Architecture & Threat Model](docs/security.md)
- [Contributing Guidelines](CONTRIBUTING.md)

---

## 📜 License

Spic is open-source software licensed under the **[MIT License](LICENSE)**.
