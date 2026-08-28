# ⚙️ Spic Configuration Guide

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
    "silence_duration_seconds": 1.0,
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
    "provider": "ollama",
    "model": "llama3.2:3b",
    "api_key": null,
    "base_url": "http://localhost:11434",
    "temperature": 0.05,
    "enable_smart_mode_default": false,
    "system_prompt": "You are a voice-to-text post-processor and conversational editor embedded in the OS. Clean and format spoken text into natural written English with proper capitalization and punctuation. Discard superseded phrases and apply conversational self-corrections."
  },
  "injection": {
    "method": "auto",
    "restore_clipboard": true,
    "typing_delay_ms": 2
  },
  "ui": {
    "show_hud": true,
    "hud_theme": "red_waveform",
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
    "hold_stream_dictation": "<RightControl>",
    "hold_trigger_delay_ms": 500
  }
}
```

---

## 2. Stream Dictation Configuration (`stream`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `chunk_pause_threshold_seconds` | `float` | `0.45` | Silence duration in seconds required to trigger a live stream chunk slice. |
| `max_chunk_duration_seconds` | `float` | `8.0` | Maximum speech duration before forcing a chunk transcription. |
| `smart_spacing` | `bool` | `true` | Automatically formats spaces and transitions between sequential stream chunks. |

---

## 3. Shortcuts Configuration (`shortcuts`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `fast_dictation` | `string` | `"<Control><Alt>space"` | Hotkey for instant toggle voice dictation with rule cleaning. |
| `smart_copilot` | `string` | `"<Control><Super>space"` | Hotkey for smart LLM voice copilot with self-corrections. |
| `hold_stream_dictation` | `string` | `"<RightControl>"` | Hotkey to hold for continuous On-the-GO stream dictation. |
| `hold_trigger_delay_ms` | `int` | `500` | Minimum hold duration in milliseconds before activating stream dictation (cancels accidental taps). |

---

## 4. LLM Provider Configurations

### A. Local Ollama (100% Offline & Private)

Ensure Ollama is running and pull the recommended 3B model:
```bash
ollama pull llama3.2:3b
```

Configure `~/.config/spic/config.json`:
```json
{
  "llm": {
    "provider": "ollama",
    "model": "llama3.2:3b",
    "base_url": "http://localhost:11434"
  }
}
```

---

### B. Google Gemini REST API

Configure your API key (passed securely in HTTP headers via `x-goog-api-key`):
```json
{
  "llm": {
    "provider": "gemini",
    "model": "gemini-2.0-flash",
    "api_key": "AIza..."
  }
}
```

---

### C. Groq Cloud (Ultra-Fast <250ms Inference)

```bash
export GROQ_API_KEY="gsk_..."
```

Or in `config.json`:
```json
{
  "llm": {
    "provider": "groq",
    "model": "llama-3.1-8b-instant",
    "api_key": "gsk_..."
  }
}
```

---

### D. OpenAI / Anthropic Claude / OpenRouter

- **OpenAI:** `"provider": "openai"`, `"model": "gpt-4o-mini"`, `"api_key": "sk-..."`
- **Anthropic:** `"provider": "anthropic"`, `"model": "claude-3-5-haiku-20241022"`, `"api_key": "sk-ant-..."`
- **OpenRouter:** `"provider": "openrouter"`, `"model": "meta-llama/llama-3.3-70b-instruct"`
