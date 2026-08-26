# Spic: The Native, Zero-Lag Linux Voice Copilot

## Problem Statement
How might we build an ultra-lightweight, 100% local (with optional cloud API fallback) Linux background daemon that captures speech anywhere in the OS without mic collisions, refines thoughts into clean text or actions, and injects them instantly into the active window on CPU-constrained hardware?

---

## Recommended Direction

Spic is designed as a modular, resource-conscious Linux background service with a three-layer architecture:
1. **Audio & Trigger Layer:**
   - Push-to-talk / toggle trigger configured via GNOME Global Shortcuts / evdev socket.
   - Non-blocking audio tap into PipeWire via `pw-record` / `sounddevice` with RNNoise noise suppression and real-time Voice Activity Detection (VAD).
   - Never locks ALSA hardware, allowing seamless coexistence with Zoom, Discord, and Google Meet.

2. **Dual-Path Speech & Intelligence Engine:**
   - **Path A (Fast Dictation - Sub-300ms):** Audio streams into `whisper.cpp` (tiny.en / base.en) and passes through a zero-overhead regex rule engine that handles verbal commands (*"delete that"*, *"new paragraph"*, *"scratch last word"*), filler word removal (*"um"*, *"uh"*), and auto-punctuation.
   - **Path B (Smart Interpreter / Copilot Mode):** Triggered by an explicit modifier or hotkey. Raw transcribed text is piped to an LLM provider:
     - **Local:** Ollama (e.g., `qwen3:8b`, `qwen2.5:1.5b`, `llama3.2:1b`).
     - **Cloud API Fallback:** OpenAI, Groq, OpenRouter, Anthropic, or Gemini API keys (for blazing-fast <500ms cloud inference when on low-power battery).
     - System prompt instructs the LLM to act as a pure text-transform engine (e.g., reformatting unstructured brainstorming into clean bullet points, fixing syntax, converting spoken pseudo-code into actual code, or drafting formal replies).

3. **Universal Wayland/X11 HUD & Injection:**
   - Floating translucent red waveform HUD overlay (GTK4 / Layer-Shell / PyQt) providing visual feedback during listening and processing.
   - Direct universal cursor injection via Linux `/dev/uinput` virtual keyboard and `wl-copy` / clipboard synchronization fallback.

---

## Key Assumptions to Validate
- [ ] **Wayland Input Injection Reliability:** Validate that `/dev/uinput` or `ydotool` / clipboard paste reliably types into GTK, Qt, Electron (VS Code, Slack, Discord), and terminal emulators without focus loss.
- [ ] **PipeWire Concurrency:** Verify that tapping the default PipeWire microphone source introduces zero audio degradation or stuttering to active VoIP calls (e.g., Zoom/Google Meet).
- [ ] **CPU Dictation Latency:** Validate that `whisper.cpp` (base.en/tiny.en) completes 3-5 seconds of voice transcription in <400ms on CPU without spinning fans.
- [ ] **LLM Pipeline Token Latency:** Measure local Ollama vs. Cloud API (Groq/OpenAI) speed for short smart edits to ensure user experience remains fluid.

---

## MVP Scope

### In Scope (MVP)
- **Audio Capture:** PipeWire recording with automatic silence trimming (VAD) and noise filtering.
- **Local STT:** Fast `whisper.cpp` (or `faster-whisper`) engine running locally on CPU/GPU.
- **Smart Rule Cleaner:** Automatic removal of verbal fillers (*"um"*, *"ah"*, *"like"*, *"you know"*) and speech-based edits (*"delete that"*, *"scratch that"*, *"clear that"*).
- **Dual LLM Backend (Local + Cloud API):**
  - Local Ollama backend (`qwen3:8b`, `llama3.2:1b`, etc.).
  - Configurable Cloud API key support (Groq, OpenAI, Anthropic, Gemini, OpenRouter) with auto-switch / manual toggle in configuration.
- **Wayland Input Injector:** Direct typing into active cursor position using `uinput` / `wl-copy` clipboard synthesis.
- **HUD Indicator:** Minimal floating overlay indicating 🔴 Listening (live wave), ⚡ Processing, ✍️ Typing.
- **Configuration File:** Simple YAML/JSON config (`~/.config/spic/config.json`) for hotkeys, models, API keys, and injection modes.

### Out of Scope (For Now)
- Heavy vector database setups (ChromaDB/LanceDB) — replaced by lightweight SQLite / key-value glossary.
- Full desktop GUI settings dashboard (MVP will use clean CLI / JSON configuration).
- Screen OCR / visual desktop perception (keeping background memory under <150MB).

---

## Not Doing (and Why)
- **Continuous Always-On Wake Word Engine:** Consumes constant CPU cycles and poses privacy/security concerns. Push-to-talk / toggle hotkey provides absolute user control and zero idle resource usage.
- **Direct ALSA / OSS Hardware Hooks:** Avoided to eliminate mic device locking and collision with conferencing applications.
- **Heavy Vector Database for Context:** Vector embeddings on CPU introduce high RAM consumption and query latency; simple active window title sniffing + local glossary provides 90% of the value at 1% of the cost.

---

## Open Questions & Configuration
- Default hotkey binding preference (e.g., `Super+Shift+Space`, `Ctrl+Alt+Space`, or `F8`).
- Preferred fallback injection method when `uinput` permissions are missing (e.g., automatic udev rule setup vs. clipboard paste).
