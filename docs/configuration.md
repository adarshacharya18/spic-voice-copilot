# ⚙️ Spic Complete Configuration Guide

Spic stores its configuration in JSON format at:
```
~/.config/spic/config.json
```
The configuration file and directory are secured with strict `0600`/`0700` POSIX permissions (accessible only by your Linux user).

---

## 1. Full Configuration Schema & Default Values

```json
{
  "audio": {
    "sample_rate": 16000,
    "channels": 1,
    "device_index": null,
    "silence_duration_seconds": 5.0,
    "vad_energy_threshold": 0.015,
    "enable_noise_reduction": true
  },
  "stt": {
    "engine": "faster-whisper",
    "model_size": "base.en",
    "device": "cpu",
    "compute_type": "int8",
    "language": "en"
  },
  "llm": {
    "provider": "gemini",
    "model": "gemini-3.5-flash",
    "api_key": null,
    "base_url": "http://localhost:11434",
    "temperature": 0.1,
    "enable_smart_mode_default": false,
    "system_prompt": "You are an invisible voice-to-text interpreter embedded in the user's OS. Your task is to take spoken transcriptions and output ONLY the final intended text to paste. Clean up fillers ('um', 'uh', 'like'), correct typos, and execute inline edits. If the user says 'scratch that' or 'delete that sentence', do not include the deleted statement. Never explain your reasoning. Output ONLY the resulting text."
  },
  "injection": {
    "method": "auto",
    "restore_clipboard": true,
    "typing_delay_ms": 5
  },
  "ui": {
    "show_hud": true,
    "hud_theme": "red_waveform",
    "hud_position": "top_center",
    "hud_width": 220,
    "hud_height": 64
  },
  "stream": {
    "chunk_pause_threshold_seconds": 0.45,
    "max_chunk_duration_seconds": 8.0,
    "smart_spacing": true
  },
  "shortcuts": {
    "fast_dictation": "<Control><Alt>space",
    "smart_copilot": "<Control><Super>space",
    "activity_termination_grace_seconds": 0.25,
    "mouse_move_threshold_px": 15.0
  }
}
```

---

## 2. Speech-to-Text (STT) Options (`stt`)

| Parameter | Type | Default | Options | Description |
|---|---|---|---|---|
| `engine` | `string` | `"faster-whisper"` | `"faster-whisper"`, `"gemini-live"`, `"whisper-cpp"`, `"cloud-api"` | Speech recognition driver. |
| `model_size` | `string` | `"base.en"` | `"tiny.en"`, `"base.en"`, `"small.en"`, `"distil-medium.en"` | Model size for local Whisper STT. |
| `device` | `string` | `"cpu"` | `"cpu"`, `"cuda"`, `"auto"` | Compute device. |
| `compute_type` | `string` | `"int8"` | `"int8"`, `"float32"`, `"float16"` | CPU / GPU quantization level. |
| `language` | `string` | `"en"` | Any ISO 639-1 code | Target transcription language. |

### STT Engines:
1. **`"faster-whisper"` (100% Offline):** Runs local Whisper via CTranslate2. Zero internet requirement.
2. **`"gemini-live"` (Google Cloud Live API):** Connects to `gemini-3.5-transcribe-live` over bidirectional WebSocket. Automatically falls back to local Whisper if offline or API key is unset.

---

## 3. Smart Voice Copilot LLM Options (`llm`)

| Parameter | Type | Default | Options | Description |
|---|---|---|---|---|
| `provider` | `string` | `"gemini"` | `"gemini"`, `"ollama"`, `"groq"`, `"openai"`, `"anthropic"`, `"openrouter"`, `"none"` | Active LLM reasoning provider. |
| `model` | `string` | `"gemini-3.5-flash"` | Cloud or local model ID | Model identifier. |
| `api_key` | `string \| null` | `null` | API key string | Explicit key or `null` to read from environment / `.env`. |
| `base_url` | `string` | `"http://localhost:11434"` | URL string | Base URL for Ollama or OpenAI-compatible server. |
| `temperature` | `float` | `0.1` | `0.0 - 1.0` | Sampling temperature for formatting. |

### 🛡️ 3-Tier Multi-LLM Failover Cascade
When Smart Mode (`Ctrl + Super + Space`) is triggered, Spic executes the following waterfall:
1. **Tier 1 (Configured Cloud LLM):** Google Gemini 3.5 Flash / Groq / OpenAI / Anthropic.
2. **Tier 2 (Local Offline Ollama Failover):** If Cloud API fails, hits rate limit (429), or has no key $\to$ automatically falls back to local `llama3.2:3b`.
3. **Tier 3 (Deterministic Rule Cleaner):** If Ollama is not running $\to$ automatically falls back to instant regex verbal punctuation and deletion rules. Zero speech is ever lost.

---

## 4. Multi-Source API Key Resolution

Spic resolves API keys and models automatically in the following order:
1. **Direct Config File:** `"api_key"` field in `~/.config/spic/config.json`.
2. **Environment File:** `~/.config/spic/.env` *(ideal for background systemd)*:
   ```bash
   cat << 'EOF' > ~/.config/spic/.env
   GEMINI_API_KEY="AIzaSyYourActualGoogleKey"
   GEMINI_MODEL="gemini-3.5-flash"
   EOF
   chmod 600 ~/.config/spic/.env
   ```
3. **Shell Environment Variables:**
   - `export GEMINI_API_KEY="..."` or `export GOOGLE_API_KEY="..."`
   - `export GROQ_API_KEY="..."`
   - `export OPENAI_API_KEY="..."`
   - `export ANTHROPIC_API_KEY="..."`

---

## 5. Live Streaming Dictation Options (`stream`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `chunk_pause_threshold_seconds` | `float` | `0.45` | Natural pause duration (in seconds) required to slice and transcribe speech chunk. |
| `max_chunk_duration_seconds` | `float` | `8.0` | Maximum continuous speech duration before forcing a chunk boundary. |
| `smart_spacing` | `bool` | `true` | Automatically handles whitespace and punctuation between sequential streamed chunks. |

---

## 6. Global Shortcuts & Activity Watcher (`shortcuts`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `fast_dictation` | `string` | `"<Control><Alt>space"` | Shortcut for Fast Voice Dictation (On-the-GO Streaming). |
| `smart_copilot` | `string` | `"<Control><Super>space"` | Shortcut for Smart Voice Copilot (LLM Reasoning). |
| `activity_termination_grace_seconds` | `float` | `0.25` | Grace window (in seconds) ignoring keypresses immediately upon hotkey activation. |
| `mouse_move_threshold_px` | `float` | `15.0` | Distance in pixels of physical mouse/touchpad movement required to auto-stop recording. |

---

## 7. Universal Linux Input Injection (`injection`)

| Parameter | Type | Default | Options | Description |
|---|---|---|---|---|
| `method` | `string` | `"auto"` | `"auto"`, `"uinput"`, `"clipboard_xdotool"`, `"clipboard_wtype"`, `"clipboard_ydotool"` | Method used to inject text. |
| `restore_clipboard` | `bool` | `true` | Automatically restores original user clipboard contents after paste simulation. |
| `typing_delay_ms` | `int` | `5` | Inter-keystroke typing delay in milliseconds for hardware uinput simulation. |

---

## 8. Floating Wave HUD Options (`ui`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `show_hud` | `bool` | `true` | Enable or disable the floating wave HUD overlay. |
| `hud_theme` | `string` | `"red_waveform"` | Color palette (`"red_waveform"`, `"crimson_flow"`, `"amber_flame"`). |
| `hud_position` | `string` | `"top_center"` | Screen positioning (`"top_center"`, `"bottom_center"`, `"center"`). |
| `hud_width` | `int` | `220` | HUD window width in pixels. |
| `hud_height` | `int` | `64` | HUD window height in pixels. |

---

## 9. CLI Testing & Management Reference

| Command | Purpose |
|---|---|
| `python3 -m spic.cli start` | Launch daemon in interactive foreground mode. |
| `python3 -m spic.cli autostart --enable` | Enable systemd background service on boot. |
| `python3 -m spic.cli autostart --status` | Check systemd background daemon status. |
| `python3 -m spic.cli autostart --logs` | Tail live background logs. |
| `python3 -m spic.cli test-stt --duration 4` | Run side-by-side benchmark of Local Whisper vs Gemini Live. |
| `python3 -m spic.cli test-llm --input "..."` | Test LLM interpretation and self-correction rules. |
| `python3 -m spic.cli test-mic` | Test microphone level and PipeWire audio stream. |
| `python3 -m spic.cli test-ui` | Test floating wave HUD animation cycles. |
| `python3 -m spic.cli test-injection` | Test hardware typing into active cursor location. |
| `python3 -m spic.cli memory --search "..."` | Search cross-agent persistent memory facts. |
| `python3 -m spic.cli setup-shortcuts` | Guide GNOME global hotkey binding and conflict detection. |
