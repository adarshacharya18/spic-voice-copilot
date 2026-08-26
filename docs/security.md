# 🛡️ Spic Security Architecture & Safe Usage Rules

## 1. Threat Model & Trust Boundaries

Spic operates as a background service on Linux with direct access to audio devices and desktop input synthesis. To ensure system security and user privacy, Spic treats every external input, network response, and desktop boundary with defense-in-depth controls.

```
                    ┌────────────────────────┐
                    │ PipeWire Audio Stream  │
                    └───────────┬────────────┘
                                │ (Non-blocking, shared stream)
                                ▼
                    ┌────────────────────────┐
                    │  Spic Daemon (User)    │ ◄─── Restricted Socket (0600 + UID Check)
                    └─────┬────────────┬─────┘
                          │            │
         (Local int8 STT) │            │ (Local Ollama / HTTPS Cloud API)
                          ▼            ▼
                    ┌────────────────────────┐
                    │  Sanitization Filter   │ (Strips ANSI codes, non-printables & \r\n)
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ Active Window (Target) │ (Universal Paste via uinput/wl-copy)
                    └────────────────────────┘
```

---

## 2. STRIDE Security Matrix & Implemented Mitigations

| Threat Category | Potential Attack / Failure Vector | Implemented Mitigation in Spic |
| :--- | :--- | :--- |
| **Spoofing** | Another local user sending unauthorized IPC commands to trigger Spic. | **Peer UID Check:** IPC Unix socket verifies `SO_PEERCRED` ensuring only the current user's UID can trigger commands. Socket file permissions are locked to `0600`. |
| **Tampering** | Injected ANSI escape sequences or malicious control codes manipulating terminal state. | **Input Sanitizer:** All STT/LLM text passes through `_sanitize_text()`, stripping raw terminal escape codes (`\x1b[...]`) and non-printable control characters. |
| **Information Disclosure** | Leakage of Cloud LLM API keys (`GROQ_API_KEY`, etc.) or recorded audio files. | **File Permissions:** `~/.config/spic/config.json` is created with strict `0600` permissions (user read/write only).<br>**RAM-Only Audio:** Audio buffers are held strictly in transient RAM (`np.ndarray`) and never written to `/tmp` as unencrypted WAV files. |
| **Denial of Service** | Infinite recording buffer consuming all system RAM or runaway LLM token generation. | **Audio Max-Duration Cap:** `AudioRecorder` automatically stops recording after 60 seconds.<br>**Token Bounds:** Input text is capped at 4,000 characters and LLM responses at 1,024 tokens with strict timeouts. |
| **Elevation of Privilege** | Unintentional command execution in open terminal or `sudo` prompt. | **Trailing Newline Stripping:** Trailing `\n` is automatically stripped prior to injection so voice text never auto-executes commands without the user pressing Enter. |

---

## 3. Rules for Safe Usage

### ⚠️ Rule 1: Caution in Root Terminals & Password Prompts
- When focused on an administrative terminal (`sudo -i`) or password prompt, avoid triggering voice dictation to prevent unintended text input.
- Spic automatically strips trailing newlines so no command will execute automatically, but always visually verify text before hitting `Enter` in shells.

### 🔑 Rule 2: API Key Security
- If using Cloud LLMs (Groq, OpenAI, Gemini, Anthropic), store your keys in environment variables or in `~/.config/spic/config.json`.
- The configuration directory `~/.config/spic` is restricted to `chmod 700` and `config.json` to `chmod 600`. Never check `config.json` into a public Git repository.

### 🎙️ Rule 3: Microphone Privacy & Indicators
- Spic displays a visible floating HUD overlay (🔴 red glowing wave) whenever the microphone is actively recording.
- Audio capture is **Push-to-Talk / Toggle-Only**. Spic never performs ambient always-on listening.

### 📋 Rule 4: System Clipboard Preservation
- Spic saves and asynchronously restores your existing system clipboard within ~600ms of pasting to ensure your clipboard history is not permanently overwritten.

---

## 4. Pre-Flight Security Verification Checklist

Before starting the daemon, you can verify your security settings:

- [x] **Config Permissions:** `ls -ld ~/.config/spic` is `drwx------` (`0700`) and `config.json` is `-rw-------` (`0600`).
- [x] **IPC Socket Isolation:** Socket path is in `$XDG_RUNTIME_DIR/spic` or `~/.cache/spic` with UID authentication.
- [x] **No Disk Artifacts:** Audio is held strictly in RAM and discarded immediately upon transcription.
- [x] **Subprocess Safety:** All shell/subprocess commands pass explicit argument arrays (`shell=False`) with strict timeouts.
- [x] **Input Sanitization:** Control codes and ANSI escape sequences are filtered before injection.
