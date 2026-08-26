# ⚙️ Spic Configuration Guide

Spic stores its configuration in JSON format at:
```
~/.config/spic/config.json
```
The configuration file is secured with strict `0600` file permissions (accessible only by your Linux user).

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
    "temperature": 0.0,
    "enable_smart_mode_default": false,
    "system_prompt": "You are a voice-to-text dictation assistant embedded in the OS. Clean and format the spoken text into natural written English with proper capitalization and punctuation. CRITICAL: Never drop leading pronouns or words (such as 'I', 'We', 'They', 'He', 'She', 'The'). Keep numbers and times in standard numeric format."
  },
  "injection": {
    "method": "auto",
    "restore_clipboard": true,
    "typing_delay_ms": 2
  },
  "ui": {
    "show_hud": true,
    "hud_theme": "red_waveform",
    "hud_width": 170,
    "hud_height": 42
  },
  "shortcuts": {
    "fast_dictation": "<Control><Alt>space",
    "smart_copilot": "<Control><Super>space"
  }
}
```

---

## 2. LLM Provider Configurations

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

### B. Groq Cloud (Ultra-Fast <250ms Inference)

Set your environment variable or add your key directly into the configuration:

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

### C. Google Gemini

```bash
export GEMINI_API_KEY="AIzaSy..."
```

Or in `config.json`:
```json
{
  "llm": {
    "provider": "gemini",
    "model": "gemini-2.0-flash",
    "api_key": "AIzaSy..."
  }
}
```

---

### D. OpenAI / OpenRouter / Anthropic

```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key": "sk-..."
  }
}
```

---

## 3. STT Model Options (`stt.model_size`)

| Model Size | RAM Usage | Speed (CPU) | Recommended For |
|---|---|---|---|
| `tiny.en` | ~200 MB | Ultra Fast (<150ms) | Low-spec laptops |
| `base.en` (Default) | ~400 MB | Fast (~250ms) | General daily dictation |
| `small.en` | ~1.0 GB | Moderate (~500ms) | High accuracy requirements |
| `medium.en` | ~2.5 GB | Slower (~1.2s) | Technical & complex vocabulary |

---

## 4. UI Customization (`ui`)

- `hud_width`: Width of the floating pill (default: `170px`).
- `hud_height`: Height of the floating pill (default: `42px`).
- `show_hud`: Set to `false` to run in completely invisible headless mode.

---

## 5. Hotkeys & Shortcut Management (`shortcuts`)

Spic supports custom system-level shortcuts with built-in GNOME desktop conflict detection:

| Field | Default Value | Description |
|---|---|---|
| `fast_dictation` | `<Control><Alt>space` | Global trigger for instant voice dictation (<300ms) |
| `smart_copilot` | `<Control><Super>space` | Global trigger for smart LLM voice copilot |

### Shortcut Management CLI Commands:

```bash
# 1. Interactive configuration wizard (recommends free keys & warns on conflicts)
python3 -m spic.cli shortcuts

# 2. List all verified free & unassigned hotkeys on your desktop
python3 -m spic.cli shortcuts --list-free

# 3. Check if a specific shortcut has desktop conflicts
python3 -m spic.cli shortcuts --check "ctrl+alt+m"

# 4. Set custom shortcuts directly
python3 -m spic.cli shortcuts --fast "ctrl+alt+m" --smart "ctrl+super+k"
```

