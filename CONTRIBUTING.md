# Contributing to Spic

Thank you for your interest in contributing to **Spic** — the open-source, privacy-first native Linux voice copilot!

We welcome all contributions: bug reports, feature requests, documentation improvements, performance optimizations, and code contributions.

---

## 🛠️ Development Setup

### 1. Prerequisites
- **Operating System:** Ubuntu 22.04+ or modern Linux distribution (Wayland or X11)
- **Python:** Python 3.10+
- **System Audio:** PipeWire (`pw-record`) or PulseAudio
- **Build Tools:** `gcc`, `make`, `pkg-config`

### 2. Clone and Setup Environment

```bash
# Clone the repository
git clone https://github.com/your-username/spic.git
cd spic

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Configure /dev/uinput permissions for Wayland hardware typing
./scripts/setup_uinput.sh
```

---

## 🧪 Testing and Verification

Run the built-in diagnostic and test suites before submitting PRs:

```bash
# Test microphone audio capture
python3 -m spic.cli test-mic

# Test rule cleaner and conversational self-corrections
python3 -m spic.cli test-rules

# Test Speech-to-Text inference
python3 -m spic.cli test-stt

# Test LLM smart interpretation
python3 -m spic.cli test-llm --input "I was working in the morning till 8pm. No make it 9pm."

# Test Wayland hardware text injection
python3 -m spic.cli test-injection --text "✨ Spic Test Injection"
```

---

## 📐 Architecture Guidelines

When contributing code, please respect the modular architectural boundaries:

- `spic/audio/`: Audio recording via native PipeWire streaming and VAD. Do not introduce blocking loops on the main thread.
- `spic/stt/`: Local speech recognition (`faster-whisper`). Must support CPU `int8` quantization without exceeding CPU thread limits.
- `spic/interpreter/`:
  - `rule_cleaner.py`: Zero-latency deterministic parser for voice commands (*"scratch that"*, self-corrections, verbal punctuation).
  - `llm_router.py`: Pluggable router supporting local Ollama (`llama3.2:3b`, `qwen2.5`) and cloud providers (Groq, Gemini, OpenAI, Claude).
- `spic/injector/`: Wayland/X11 universal text injector using Linux Kernel `/dev/uinput` virtual hardware keyboard.
- `spic/ui/`: 60 FPS floating Tkinter wave visualizer. Must maintain non-blocking asynchronous event loop.

---

## 🔒 Security & Privacy Rules

1. **Zero Unintended Network Calls:** Fast dictation mode and local Ollama mode must never send audio or transcriptions over the internet.
2. **Input Sanitization:** All injected text must be sanitized against ANSI terminal escape sequence injections.
3. **IPC Security:** Unix Domain Sockets must reside in `$XDG_RUNTIME_DIR/spic` with `0600` permissions and Linux UID verification (`SO_PEERCRED`).

---

## 🚀 Submitting a Pull Request

1. Fork the repository and create your branch from `main`:
   ```bash
   git checkout -b feature/my-cool-feature
   ```
2. Commit your changes with clear, semantic commit messages:
   ```bash
   git commit -m "feat(ui): add glowing particle trail to processing wave"
   ```
3. Push to your fork:
   ```bash
   git push origin feature/my-cool-feature
   ```
4. Open a Pull Request on GitHub with a description of changes and verification steps.

---

## 📜 Code of Conduct

Please be respectful, collaborative, and constructive in all community interactions.
