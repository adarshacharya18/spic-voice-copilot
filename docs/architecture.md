# 🏛️ Spic Technical Architecture & Design

**Spic** is an ultra-low latency, privacy-first voice copilot engineered specifically for Linux desktop environments (GNOME Wayland and X11). It seamlessly converts spoken voice into clean, polished, context-aware written text and types it directly into whichever application window currently has focus.

---

## 1. High-Level System Architecture

```mermaid
flowchart TD
    subgraph Input_Layer ["🎤 Audio & Trigger Layer"]
        Hotkey["GNOME Global Hotkeys<br>(Ctrl+Alt+Space / Ctrl+Super+Space)"] -->|IPC Socket Trigger| Daemon["Spic Daemon<br>(Unix Domain Socket 0600)"]
        Sensor["ActivityTerminationWatcher<br>(Keypress & Mouse Vector Sensor)"] -->|Instant Finish Signal| Daemon
        Mic["Microphone"] -->|PipeWire 16kHz s16 PCM| StreamRec["Stream Audio Recorder<br>(pw-record + Pause Slicer 450ms)"]
    end

    subgraph Visual_Layer ["✨ Ambient Motion Layer"]
        Daemon -->|60 FPS Wave States| HUD["Floating Translucent HUD<br>(Spring Drop & Harmonic Wave Ribbon)"]
    end

    subgraph Intelligence_Layer ["🧠 Cognitive Memory & Speech Pipeline"]
        StreamRec -->|Speech Slices on Pauses| Worker["Stream Transcription Worker<br>(Async FIFO Queue + Rolling Prompt)"]
        Worker --> STT["Local STT Engine<br>(faster-whisper CPU int8)"]
        
        STT -->|Raw Speech| Router["Interpreter & Router"]
        Router -->|Fast Mode (On-the-GO)| Spacing["Rule Cleaner & Smart Chunk Spacing"]
        Router -->|Smart Mode| LLM["Few-Shot LLM Router<br>(Ollama llama3.2:3b / Groq / Gemini / OpenAI)"]
        
        Memory[(CoALA Cognitive Memory<br>SQLite + FTS5 Hybrid Store 0600)] <-->|Context Synthesis & Recall| LLM
    end

    subgraph Output_Layer ["⌨️ Universal Wayland Injection Layer"]
        Spacing -->|Live Stream Chunks| Injector["Universal Input Injector"]
        LLM -->|Polished Output| Injector
        Injector -->|Hardware Key Events| UInput["Linux Kernel /dev/uinput<br>(Spic Virtual Keyboard)"]
        UInput -->|Direct Hardware Keystrokes| ActiveApp["Active Focused Window<br>(VS Code, Terminal, Browser, Slack)"]
    end
```

---

## 2. Core Subsystems

### A. Fast Mode: On-the-GO Live Continuous Streaming (`spic.audio`, `spic.stt`)
- **Real-Time VAD Pause Slicing:** Continuous audio captured via PipeWire is analyzed in 50ms frames using RMS energy tracking. Every natural pause ($450\text{ms}$) or chunk maximum ($8.0\text{s}$) slices a speech chunk and immediately passes it to the transcription queue.
- **Async FIFO Transcription Worker (`StreamTranscriptionWorker`):** Transcribes audio slices asynchronously in background threads ($<180\text{ms}$) and types each chunk **live at the cursor** while you continue speaking!
- **Smart Inter-Chunk Spacing:** Evaluates boundary tokens to manage spacing and punctuation dynamically (e.g. prepending whitespace before words while adhering directly to commas, periods, and colons).

### B. Smart Mode: Whole-Utterance LLM Reasoning (`spic.interpreter`, `spic.memory`)
- **Full Context Capture:** Captures the complete spoken thought before invoking the LLM, giving the model full conversational context.
- **Few-Shot Self-Correction Architecture:** Detects conversational repairs, phrase retries, and deletions (*"select screenshot in the left drawer from the drawer"* $\to$ *"Select screenshot from the drawer"*).
- **CoALA Cognitive Memory Recall:** Merges relevant semantic preferences and episodic memory items into prompt context.

### C. Tap-to-Start, Action-to-Finish Engine (`spic.shortcuts`)
- **Zero Key Holding:** Users tap `Ctrl + Alt + Space` or `Ctrl + Super + Space` once to activate. Hands remain completely free during speech.
- **Gesture & Hardware Termination:** The `ActivityTerminationWatcher` activates with a **250ms release grace period**:
  - The instant the user **presses any key** (e.g. `Space`, `Enter`, or resumes typing), **moves the mouse** ($>15\text{px}$ vector), or **clicks**, recording instantly terminates and returns full keyboard control.
  - **Silence VAD Fallback:** If no manual action is taken, a 5.0s silence detector automatically finalizes the input.

### D. Universal Wayland Text Injector (`spic.injector`)
- **Kernel Virtual Keyboard:** Emits hardware scancodes through `/dev/uinput` at **1.5ms per character** to type directly into focused applications without depending on X11 or XTest extensions.
- **Escape Sanitization:** Strips ANSI terminal escape sequences and unprintable control characters to prevent terminal command injection.

### E. Ambient Floating HUD (`spic.ui`)
- **Physics Transitions:** Features a spring-overshoot drop transition (`ease_out_back`) on activation and an upward glide collapse (`ease_in_cubic`) upon completion.
- **60 FPS Harmonic Waves:** Renders multi-layered composite sine splines with Gaussian edge envelope damping:
  - **Listening Wave:** Crimson Red (`#FF3B30`) & Coral Sunset audio-reactive harmonic splines.
  - **Thinking Wave:** Electric Cyan (`#00F2FE`) & Neon Purple traveling quantum flow ribbon.
  - **Done Wave:** Emerald Green (`#10B981`) settling pulse.

---

## 3. End-to-End Latency Profile

| Stage | Fast Mode (On-the-GO Streaming) | Smart Copilot (LLM Reasoning) |
|---|---|---|
| **Audio Capture & Slicing** | Sliced every 450ms pause | Full thought capture |
| **STT (Whisper Base CPU int8)** | ~180ms per chunk | ~250ms |
| **Interpretation** | <1ms (Rule Cleaner + Spacing) | ~2.5s (Ollama) / ~250ms (Groq) |
| **Hardware Injection (uinput)** | ~20ms per chunk | ~50ms |
| **Typing Experience** | **Live streaming chunk-by-chunk at cursor** | **Polished paragraph injected all-at-once** |
