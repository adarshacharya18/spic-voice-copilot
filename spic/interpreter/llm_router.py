"""LLM interpretation router supporting local Ollama and Cloud API providers."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
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
        self._last_notify_time = 0.0

    def _notify_missing_provider(self, title: str, details: str) -> None:
        """Send a friendly rate-limited desktop notification when an LLM provider or model is missing."""
        now = time.time()
        if now - self._last_notify_time < 30.0:  # Rate limit: max once every 30 seconds
            return
        self._last_notify_time = now

        try:
            msg = f"{details}\nUsing fast rule cleaner for this input."
            subprocess.run(
                ["notify-send", "-a", "Spic Voice Copilot", "-i", "dialog-information", f"💡 {title}", msg],
                check=False,
                timeout=1.0,
            )
        except Exception:
            pass

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

    FEW_SHOT_EXAMPLES = [
        {"role": "user", "content": "in the left drawer from the drawer"},
        {"role": "assistant", "content": "From the drawer."},
        {"role": "user", "content": "I want to order pizza, actually sushi"},
        {"role": "assistant", "content": "I want to order sushi."},
        {"role": "user", "content": "please send the document to Alice scratch that send it to Bob"},
        {"role": "assistant", "content": "Please send the document to Bob."},
        {"role": "user", "content": "we should schedule the call for three PM, no make that four thirty PM"},
        {"role": "assistant", "content": "We should schedule the call for 4:30 PM."},
        {"role": "user", "content": "select screenshot in the left drawer from the drawer"},
        {"role": "assistant", "content": "Select screenshot from the drawer."},
    ]

    def _build_messages(self, text: str) -> list[dict[str, str]]:
        """Build structured few-shot message payload augmented with user memory context."""
        system_content = (
            "You are a voice-to-text post-processor and conversational editor embedded in the OS. "
            "Your job is to transform raw spoken audio transcripts into clean, intended written text.\n\n"
            "CRITICAL EDITING RULES:\n"
            "1. Conversational Self-Corrections & Retries:\n"
            "   Speakers often change their minds mid-sentence, restart a clause, or correct a word.\n"
            "   Always identify what the speaker intended and discard superseded phrases.\n"
            "   - 'in the left drawer from the drawer' -> 'From the drawer.'\n"
            "   - 'meet on Friday, actually Monday' -> 'Meet on Monday.'\n"
            "   - 'I want pizza, actually sushi' -> 'I want sushi.'\n"
            "2. Inline Voice Edits:\n"
            "   If the speaker says 'scratch that', 'delete that', 'never mind', remove the cancelled text.\n"
            "   - 'send the report today scratch that send it tomorrow' -> 'Send the report tomorrow.'\n"
            "3. Grammar & Formatting:\n"
            "   - Strip filler words ('um', 'uh', 'you know').\n"
            "   - Keep numbers, times, and dates in standard numeric format ('9:00 AM', '$50', '10 copies').\n"
            "   - Never drop pronouns or subjects ('I', 'We', 'They', 'He', 'She').\n"
            "4. Output Format:\n"
            "   Output ONLY the final cleaned text without quotes or explanations."
        )

        try:
            mem_ctx = self.memory.prepare_agent_context(text, limit_per_type=2)
            if mem_ctx.summary_prompt:
                system_content += f"\n\nUSER MEMORY CONTEXT:\n{mem_ctx.summary_prompt}"
        except Exception:
            pass

        messages = [{"role": "system", "content": system_content}]
        messages.extend(self.FEW_SHOT_EXAMPLES)
        messages.append({"role": "user", "content": text})
        return messages

    def _call_ollama(self, text: str) -> str:
        """Call local Ollama instance via HTTP API with few-shot formatting."""
        url = f"{self.config.base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.config.model,
            "messages": self._build_messages(text),
            "stream": False,
            "options": {
                "temperature": 0.05,
                "num_predict": 128,
                "num_thread": 4,
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("message", {}).get("content", "").strip()
            return self._sanitize_llm_output(result, original_text=text)
        except requests.exceptions.ConnectionError:
            self._notify_missing_provider(
                "Ollama Not Running",
                "Ollama is not running locally. To enable local AI: start Ollama or run 'ollama run llama3.2:3b'.",
            )
            raise
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 404:
                self._notify_missing_provider(
                    "Ollama Model Missing",
                    f"Model '{self.config.model}' is not installed. Run 'ollama pull {self.config.model}'.",
                )
            raise

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
            "messages": self._build_messages(text),
            "temperature": self.config.temperature,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        result = data["choices"][0]["message"]["content"].strip()
        return self._sanitize_llm_output(result, original_text=text)

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
            "messages": self._build_messages(text),
            "temperature": self.config.temperature,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = data["choices"][0]["message"]["content"].strip()
        return self._sanitize_llm_output(result, original_text=text)

    def _call_anthropic(self, text: str) -> str:
        """Call Anthropic Claude API."""
        api_key = self._get_api_key(["ANTHROPIC_API_KEY", "SPIC_LLM_API_KEY"])
        if not api_key:
            raise ValueError("Anthropic API key not found. Set in config or export ANTHROPIC_API_KEY.")

        messages = self._build_messages(text)
        system_prompt = messages[0]["content"]
        chat_turns = messages[1:]

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model if self.config.model != "qwen3:8b" else "claude-3-5-haiku-20241022",
            "system": system_prompt,
            "messages": chat_turns,
            "max_tokens": 1024,
            "temperature": self.config.temperature,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = data["content"][0]["text"].strip()
        return self._sanitize_llm_output(result, original_text=text)

    def _call_gemini(self, text: str) -> str:
        """Call Google Gemini API."""
        api_key = self._get_api_key(["GEMINI_API_KEY", "GOOGLE_API_KEY", "SPIC_LLM_API_KEY"])
        if not api_key:
            raise ValueError("Gemini API key not found. Set in config or export GEMINI_API_KEY.")

        messages = self._build_messages(text)
        system_prompt = messages[0]["content"]

        contents = []
        for m in messages[1:]:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        model_name = self.config.model if self.config.model != "qwen3:8b" else "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": self.config.temperature},
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return self._sanitize_llm_output(result, original_text=text)

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
            "messages": self._build_messages(text),
            "temperature": self.config.temperature,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        result = data["choices"][0]["message"]["content"].strip()
        return self._sanitize_llm_output(result, original_text=text)

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
