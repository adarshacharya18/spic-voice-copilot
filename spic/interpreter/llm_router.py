"""LLM interpretation router supporting local Ollama and Cloud API providers."""

from __future__ import annotations

import json
import logging
import os
from typing import Optional
import requests

from spic.config import LLMConfig
from spic.interpreter.rule_cleaner import RuleCleaner
from spic.memory import AgentMemoryCoordinator

logger = logging.getLogger("spic.interpreter.llm")


class LLMRouter:
    """Routes voice transcriptions through local Ollama or Cloud LLM APIs with cognitive memory augmentation."""

    def __init__(self, config: LLMConfig, memory: Optional[AgentMemoryCoordinator] = None):
        self.config = config
        self.rule_cleaner = RuleCleaner()
        self.memory = memory or AgentMemoryCoordinator()

    def process(self, raw_text: str, force_smart_mode: Optional[bool] = None) -> str:
        """Process transcription. If smart mode is disabled, uses rule cleaner."""
        if not raw_text or not raw_text.strip():
            return ""

        # Security: Bound input text length (max 4000 characters)
        bounded_text = raw_text.strip()[:4000]

        use_smart = force_smart_mode if force_smart_mode is not None else self.config.enable_smart_mode_default

        if not use_smart or self.config.provider == "none":
            return self.rule_cleaner.clean(bounded_text)

        # Route through selected LLM provider
        try:
            if self.config.provider == "ollama":
                return self._call_ollama(bounded_text)
            elif self.config.provider == "groq":
                return self._call_groq(bounded_text)
            elif self.config.provider == "openai":
                return self._call_openai(bounded_text)
            elif self.config.provider == "anthropic":
                return self._call_anthropic(bounded_text)
            elif self.config.provider == "gemini":
                return self._call_gemini(bounded_text)
            elif self.config.provider == "openrouter":
                return self._call_openrouter(bounded_text)
            else:
                logger.warning(f"Unknown provider '{self.config.provider}', falling back to rule cleaner.")
                return self.rule_cleaner.clean(bounded_text)
        except Exception as e:
            # Mask any potential sensitive details in logs
            err_msg = str(e).split("?key=")[0]
            logger.error(f"LLM processing failed ({err_msg}). Falling back to rule-based cleaner.")
            return self.rule_cleaner.clean(bounded_text)

    def _get_api_key(self, env_var_names: list[str]) -> Optional[str]:
        """Get API key from config or environment variables."""
        if self.config.api_key:
            return self.config.api_key
        for var in env_var_names:
            val = os.environ.get(var)
            if val:
                return val
        return None

    def _call_ollama(self, text: str) -> str:
        """Call local Ollama instance via HTTP API with few-shot formatting."""
        # Pre-apply rule deletions & self-corrections
        pre_cleaned = self.rule_cleaner.clean(text)
        if not pre_cleaned:
            return ""

        url = f"{self.config.base_url.rstrip('/')}/api/chat"
        system_instructions = (
            "You are a voice-to-text dictation assistant embedded in the OS. "
            "Clean and format the spoken text into natural written English with proper capitalization and punctuation. "
            "CRITICAL RULES: "
            "1. Never drop leading pronouns or subjects (such as 'I', 'We', 'They', 'He', 'She', 'The'). "
            "2. Keep numbers and times in standard numeric format (e.g. '9 PM', '8:00 AM', '10 copies', '$50') without spelling digits as words. "
            "Output ONLY the complete refined text without quotes or explanations."
        )

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": f"Input: {pre_cleaned}\nOutput:"},
            ],
            "stream": False,
            "options": {
                "temperature": 0.05,
                "num_predict": 128,
                "num_thread": 4,
            },
        }

        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("message", {}).get("content", "").strip()
        return self._sanitize_llm_output(result, original_text=pre_cleaned)

    def _call_groq(self, text: str) -> str:
        """Call Groq Cloud API for ultra-fast inference."""
        api_key = self._get_api_key(["GROQ_API_KEY", "SPIC_LLM_API_KEY"])
        if not api_key:
            raise ValueError("Groq API key not found. Set in config or export GROQ_API_KEY.")

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model if self.config.model != "qwen3:8b" else "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": f"Clean transcription: \"{text}\""},
            ],
            "temperature": self.config.temperature,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        result = data["choices"][0]["message"]["content"].strip()
        return self._sanitize_llm_output(result)

    def _call_openai(self, text: str) -> str:
        """Call OpenAI API or custom OpenAI-compatible endpoint."""
        api_key = self._get_api_key(["OPENAI_API_KEY", "SPIC_LLM_API_KEY"])
        if not api_key:
            raise ValueError("OpenAI API key not found. Set in config or export OPENAI_API_KEY.")

        base_url = self.config.base_url or "https://api.openai.com/v1"
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model if self.config.model != "qwen3:8b" else "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": f"Clean transcription: \"{text}\""},
            ],
            "temperature": self.config.temperature,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = data["choices"][0]["message"]["content"].strip()
        return self._sanitize_llm_output(result)

    def _call_anthropic(self, text: str) -> str:
        """Call Anthropic Claude API."""
        api_key = self._get_api_key(["ANTHROPIC_API_KEY", "SPIC_LLM_API_KEY"])
        if not api_key:
            raise ValueError("Anthropic API key not found. Set in config or export ANTHROPIC_API_KEY.")

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model if self.config.model != "qwen3:8b" else "claude-3-5-haiku-20241022",
            "system": self.config.system_prompt,
            "messages": [{"role": "user", "content": f"Clean transcription: \"{text}\""}],
            "max_tokens": 1024,
            "temperature": self.config.temperature,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = data["content"][0]["text"].strip()
        return self._sanitize_llm_output(result)

    def _call_gemini(self, text: str) -> str:
        """Call Google Gemini API."""
        api_key = self._get_api_key(["GEMINI_API_KEY", "GOOGLE_API_KEY", "SPIC_LLM_API_KEY"])
        if not api_key:
            raise ValueError("Gemini API key not found. Set in config or export GEMINI_API_KEY.")

        model_name = self.config.model if self.config.model != "qwen3:8b" else "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": self.config.system_prompt}]},
            "contents": [{"parts": [{"text": f"Clean transcription: \"{text}\""}]}],
            "generationConfig": {"temperature": self.config.temperature},
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return self._sanitize_llm_output(result)

    def _call_openrouter(self, text: str) -> str:
        """Call OpenRouter API."""
        api_key = self._get_api_key(["OPENROUTER_API_KEY", "SPIC_LLM_API_KEY"])
        if not api_key:
            raise ValueError("OpenRouter API key not found. Set in config or export OPENROUTER_API_KEY.")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/spic/spic",
            "X-Title": "Spic Linux Voice Copilot",
        }
        payload = {
            "model": self.config.model if self.config.model != "qwen3:8b" else "meta-llama/llama-3.3-70b-instruct",
            "messages": [
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": f"Clean transcription: \"{text}\""},
            ],
            "temperature": self.config.temperature,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = data["choices"][0]["message"]["content"].strip()
        return self._sanitize_llm_output(result)

    def _sanitize_llm_output(self, text: str, original_text: Optional[str] = None) -> str:
        """Remove reasoning tokens, markdown code fences, prefixes, and guard pronouns."""
        clean = text.strip()

        # Remove <think>...</think> reasoning traces
        import re
        clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL).strip()

        # Remove "Output:" or "Result:" prefixes if echoed
        clean = re.sub(r"^(Output|Result|Cleaned|Transcribed|Dictation):\s*", "", clean, flags=re.IGNORECASE).strip()

        # Remove surrounding markdown code blocks if present
        if clean.startswith("```") and clean.endswith("```"):
            lines = clean.splitlines()
            if len(lines) >= 3:
                clean = "\n".join(lines[1:-1]).strip()

        # Remove surrounding quotes
        if (clean.startswith('"') and clean.endswith('"')) or (clean.startswith("'") and clean.endswith("'")):
            clean = clean[1:-1].strip()

        # Normalize internal multi-space gaps
        clean = re.sub(r"[ \t]+", " ", clean)

        # Subject / Pronoun safeguard:
        if original_text:
            orig_first = original_text.strip().split()[0] if original_text.strip().split() else ""
            clean_first = clean.split()[0] if clean.split() else ""
            # If original started with 'I' / 'We' / 'They' / 'He' / 'She' and LLM started with lowercase or dropped it
            if orig_first.lower() in ("i", "we", "he", "she", "they", "the") and clean_first.lower() != orig_first.lower():
                if clean_first.lower() in ("was", "am", "have", "had", "will", "would", "can", "could", "should", "went", "got", "worked", "working"):
                    clean = f"{orig_first} {clean}"

        return clean.strip()
