"""Configuration management for Spic voice copilot."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field


CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "spic"
CONFIG_FILE = CONFIG_DIR / "config.json"


class AudioConfig(BaseModel):
    sample_rate: int = Field(default=16000, description="Audio sample rate in Hz (16kHz recommended for Whisper)")
    channels: int = Field(default=1, description="Number of audio channels (1 = mono)")
    device_index: Optional[int] = Field(default=None, description="Audio device index (None = system default / PipeWire)")
    silence_duration_seconds: float = Field(default=1.0, description="Seconds of silence before auto-stop in toggle mode")
    vad_energy_threshold: float = Field(default=0.015, description="Energy threshold for voice activity detection")
    enable_noise_reduction: bool = Field(default=True, description="Apply lightweight noise gate and normalization")


class STTConfig(BaseModel):
    engine: Literal["faster-whisper", "whisper-cpp", "cloud-api"] = Field(
        default="faster-whisper",
        description="Speech to text engine to use"
    )
    model_size: str = Field(
        default="base.en",
        description="Whisper model size (tiny.en, base.en, small.en, distil-medium.en, etc.)"
    )
    device: Literal["cpu", "cuda", "auto"] = Field(default="cpu", description="Compute device for local STT")
    compute_type: str = Field(default="int8", description="Quantization for CPU (int8/float32) or GPU (float16)")
    language: str = Field(default="en", description="Target transcription language")


class LLMConfig(BaseModel):
    provider: Literal["ollama", "openai", "groq", "anthropic", "gemini", "openrouter", "none"] = Field(
        default="ollama",
        description="LLM provider for smart interpretation and instruction execution"
    )
    model: str = Field(
        default="qwen3:8b",
        description="Model name (e.g. qwen3:8b, llama3.2:1b, gpt-4o-mini, llama-3.3-70b-versatile, gemini-2.0-flash)"
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key for cloud providers (or set SPIC_LLM_API_KEY / OPENAI_API_KEY / GROQ_API_KEY etc.)"
    )
    base_url: Optional[str] = Field(
        default="http://localhost:11434",
        description="Base URL for Ollama or custom OpenAI-compatible endpoint"
    )
    temperature: float = Field(default=0.1, description="Sampling temperature for deterministic cleanup")
    enable_smart_mode_default: bool = Field(
        default=False,
        description="If True, routes through LLM by default. If False, uses fast rule-based cleaner by default."
    )
    system_prompt: str = Field(
        default=(
            "You are an invisible voice-to-text interpreter embedded in the user's OS. "
            "Your task is to take spoken transcriptions and output ONLY the final intended text to paste. "
            "Clean up fillers ('um', 'uh', 'like'), correct typos, and execute inline edits. "
            "If the user says 'scratch that' or 'delete that sentence', do not include the deleted statement. "
            "Never explain your reasoning. Output ONLY the resulting text."
        ),
        description="System prompt guiding LLM behavior"
    )


class InjectionConfig(BaseModel):
    method: Literal["auto", "clipboard", "uinput"] = Field(
        default="auto",
        description="Text injection method ('auto' tries uinput then falls back to clipboard paste)"
    )
    restore_clipboard: bool = Field(default=True, description="Restore previous clipboard content after pasting")
    typing_delay_ms: int = Field(default=5, description="Inter-character typing delay for uinput (ms)")


class UIConfig(BaseModel):
    show_hud: bool = Field(default=True, description="Show floating red/translucent HUD during listening/processing")
    hud_theme: Literal["red_waveform", "minimal_pill"] = Field(default="red_waveform", description="HUD style theme")
    hud_position: Literal["top_center", "middle_center", "bottom_center"] = Field(
        default="top_center",
        description="Screen placement ('top_center' for top-middle, 'middle_center' for dead-center of screen)"
    )
    hud_width: int = Field(default=190, description="Width of floating HUD window in pixels")
    hud_height: int = Field(default=46, description="Height of floating HUD window in pixels")


class StreamConfig(BaseModel):
    chunk_pause_threshold_seconds: float = Field(
        default=0.45,
        description="Pause/silence duration in seconds to trigger an on-the-go stream chunk transcription"
    )
    max_chunk_duration_seconds: float = Field(
        default=8.0,
        description="Maximum duration of a single speech chunk before forcing slice transcription"
    )
    smart_spacing: bool = Field(
        default=True,
        description="Automatically manage space and punctuation transitions between sequential stream chunks"
    )


class ShortcutsConfig(BaseModel):
    fast_dictation: str = Field(
        default="<Control><Alt>space",
        description="Global hotkey for Fast Voice Dictation (e.g. <Control><Alt>space, <Control><Alt>m)"
    )
    smart_copilot: str = Field(
        default="<Control><Super>space",
        description="Global hotkey for Smart Voice Copilot (e.g. <Control><Super>space, <Control><Shift>space)"
    )
    hold_stream_dictation: str = Field(
        default="<Super><Alt>n",
        description="Global hotkey to hold for continuous On-the-GO Stream Dictation (e.g. <Super><Alt>n, <Control><Alt>m)"
    )


class SpicConfig(BaseModel):
    audio: AudioConfig = Field(default_factory=AudioConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    injection: InjectionConfig = Field(default_factory=InjectionConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    stream: StreamConfig = Field(default_factory=StreamConfig)
    shortcuts: ShortcutsConfig = Field(default_factory=ShortcutsConfig)


def load_config() -> SpicConfig:
    """Load configuration from disk, creating default if not exists with secure permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except Exception:
        pass

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SpicConfig(**data)
        except Exception as e:
            print(f"[Spic Config] Warning: Failed to parse {CONFIG_FILE} ({e}). Using defaults.")

    config = SpicConfig()
    save_config(config)
    return config


def save_config(config: SpicConfig) -> None:
    """Save configuration to disk with restricted 0600 permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except Exception:
        pass

    # Open with exclusive user-read/write mode (0600)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    mode = 0o600
    fd = os.open(CONFIG_FILE, flags, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(config.model_dump_json(indent=2))
    except Exception:
        pass
