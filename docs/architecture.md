# 🏛️ Spic Technical Architecture & Design

**Spic** is an ultra-low latency, privacy-first voice copilot engineered specifically for Linux desktop environments (GNOME Wayland and X11). It seamlessly converts spoken voice into clean, polished, context-aware written text and types it directly into whichever application window currently has focus.

---

## 1. High-Level System Architecture

```mermaid
flowchart TD
    subgraph Input_Layer ["🎤 Audio & Trigger Layer"]
        Hotkey["GNOME Global Hotkeys<br>(Ctrl+Alt+Space / Ctrl+Super+Space)"] -->|IPC Socket Trigger| Daemon["Spic Daemon<br>(Unix Domain Socket 0600)"]
        HoldKey["Hardware Hold Listener<br>(RightControl 500ms Intent Timer)"] -->|Direct Evdev Event| Daemon
        Mic["Microphone"] -->|PipeWire 16kHz s16 PCM| StreamRec["Stream Audio Recorder<br>(pw-record + VAD Slicer)"]
    end

    subgraph Visual_Layer ["✨ Ambient Motion Layer"]
        Daemon -->|60 FPS Wave States| HUD["Floating Translucent HUD<br>(Spring Drop & Harmonic Wave Ribbon)"]
    end

    subgraph Intelligence_Layer ["🧠 Cognitive Memory & Speech Pipeline"]
        StreamRec -->|Speech Slices on Pause (450ms)| Worker["Stream Transcription Worker<br>(Async FIFO Queue + Rolling Prompt)"]
        Worker --> STT["Local STT Engine<br>(faster-whisper CPU int8)"]
        
        STT -->|Raw Speech| Router["Interpreter & Router"]
        Router -->|Fast Dictation Mode| RuleCleaner["Deterministic Rule Cleaner<br>(Deletions, Self-Corrections, Punctuation)"]
        Router -->|Smart Mode| LLM["Few-Shot LLM Router<br>(Ollama llama3.2:3b / Groq / Gemini / OpenAI)"]
        
        Memory[(CoALA Cognitive Memory<br>SQLite + FTS5 Hybrid Store 0600)] <-->|Context Synthesis & Recall| LLM
    end

    subgraph Output_Layer ["⌨️ Universal Wayland Injection Layer"]
        RuleCleaner -->|Sanitized Stream Chunks| Injector["Universal Input Injector"]
        LLM -->|Polished Output| Injector
        Injector -->|Hardware Key Events| UInput["Linux Kernel /dev/uinput<br>(Spic Virtual Keyboard)"]
        UInput -->|Direct Hardware Keystrokes| ActiveApp["Active Focused Window<br>(VS Code, Terminal, Browser, Slack)"]
    end
```

---

## 2. Core Subsystems

### A. Continuous On-the-GO Stream Dictation Pipeline (`spic.audio`, `spic.stt`)
- **Real-Time VAD Chunk Slicing:** Continuous audio captured via PipeWire is analyzed in 50ms frames using RMS energy tracking. When a natural pause ($450\text{ms}$) is detected or max chunk duration ($8.0\text{s}$) is reached, the speech slice is extracted and dispatched to the transcription worker without interrupting audio capture.
- **Async FIFO Transcription Worker (`StreamTranscriptionWorker`):** Transcribes audio slices asynchronously in background threads. Maintains a rolling prompt context of the last 200 transcribed characters (`initial_prompt`) to ensure acoustic continuity across chunks.
- **Smart Inter-Chunk Spacing:** Evaluates boundary tokens to manage spacing and punctuation dynamically (e.g. prepending whitespace before words while adhering directly to commas, periods, and colons).

### B. Hardware Key-Hold Engine & 500ms Intent Timer (`spic.shortcuts`)
- **Kernel Evdev Hook:** Monitors `/dev/input/event*` devices using Linux `evdev` to capture raw hardware keypress events with zero latency.
- **500ms Intent Activation Timer:** Prevents accidental tap flicker. If the key is tapped for $<500\text{ms}$, the timer cancels silently with zero resource usage. When held past $500\text{ms}$, the full stream dictation pipeline activates.
- **Auto-Hotplug Recovery:** Safely prunes disconnected or sleeping USB/Bluetooth keyboards (`OSError: [Errno 19]`) and auto-discovers newly plugged keyboards every 4 seconds without crashing.

### C. Multi-Agent Cognitive Memory System (`spic.memory`)
Engineered according to the **CoALA (Cognitive Architectures for Language Agents)** framework:
- **4-Tier Memory Structure:**
  1. `SEMANTIC`: Long-term facts, user preferences, names, and coding styles.
  2. `EPISODIC`: Past interactions and contextual transcripts.
  3. `PROCEDURAL`: Spoken workflows and learned macros.
  4. `WORKING`: Short-term scratchpad context per active window/session.
- **Hybrid Search Scoring:**
  $$\text{Score} = 0.50 \cdot \text{Lexical FTS5} + 0.25 \cdot e^{-\lambda \Delta t} + 0.15 \cdot \text{Importance} + 0.10 \cdot \min(1.0, \frac{\text{Count}}{10})$$
- **Isolated SQLite Storage:** Persistent database at `~/.config/spic/memory/agent_memory.db` with WAL mode and POSIX `0600` permissions.

### D. Hybrid Speech Interpreter (`spic.interpreter`)
1. **Tier 1: Fast Rule Cleaner (`RuleCleaner`)**
   - **Latency:** `<1ms` (Zero delay).
   - **Features:** Deterministic verbal punctuation parsing (*"period"* -> `.`, *"comma"* -> `,`, *"new line"* -> `\n`), conversational phrase replacements (*"in the left drawer from the drawer"* -> *"from the drawer"*), spoken phrase deletions (*"scratch that"*), and verbal filler filtering (*"um"*, *"uh"*).
2. **Tier 2: Few-Shot Smart LLM Router (`LLMRouter`)**
   - **Unified Few-Shot Architecture:** Pre-loads high-signal conversational editing demonstrations into local and cloud LLM prompts, ensuring small local models (`llama3.2:3b`) execute phrase revisions reliably.
   - **Supported Backends:** Local Ollama, Groq, OpenAI, Anthropic, Google Gemini (via `x-goog-api-key` headers), and OpenRouter.

### E. Universal Wayland Text Injector (`spic.injector`)
- **Kernel Virtual Keyboard:** Emits hardware scancodes through `/dev/uinput` at **1.5ms per character** to type directly into focused applications without depending on X11 or XTest extensions.
- **Escape Sanitization:** Strips ANSI terminal escape sequences and unprintable control characters to prevent terminal command injection.

### F. Ambient Floating HUD (`spic.ui`)
- **Physics Transitions:** Features a spring-overshoot drop transition (`ease_out_back`) on activation and an upward glide collapse (`ease_in_cubic`) upon completion.
- **60 FPS Harmonic Waves:** Renders multi-layered composite sine splines with Gaussian edge envelope damping:
  - **Listening Wave:** Crimson Red (`#FF3B30`) & Coral Sunset audio-reactive harmonic splines.
  - **Thinking Wave:** Electric Cyan (`#00F2FE`) & Neon Purple traveling quantum flow ribbon.
  - **Done Wave:** Emerald Green (`#10B981`) settling pulse.

---

## 3. End-to-End Latency Profile

| Stage | Fast Dictation (`Ctrl+Alt+Space`) | On-the-GO Stream (`Hold RightControl`) | Smart Copilot (`Ctrl+Super+Space`) |
|---|---|---|---|
| **Audio Capture & Slicing** | Streamed real-time | Sliced every 450ms pause | Streamed real-time |
| **STT (Whisper Base CPU int8)** | ~250ms | ~180ms per chunk | ~250ms |
| **Interpretation** | <1ms (Rule Cleaner) | <1ms (Smart Spacing) | ~2.5s (Ollama) / ~250ms (Groq) |
| **Hardware Injection (uinput)** | ~50ms | ~20ms per chunk | ~50ms |
| **Total Roundtrip Latency** | **~300ms** | **Live Streaming on Pauses** | **~2.8s (Local) / ~550ms (Cloud)** |
