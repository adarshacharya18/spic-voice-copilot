"""Google Gemini Live Transcribe Speech-to-Text Engine leveraging the official Gemini Live WebSocket API."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional
import numpy as np

try:
    import websockets
except ImportError:
    websockets = None

logger = logging.getLogger("spic.stt.gemini_live")

DEFAULT_MODEL = "gemini-3.5-transcribe-live"
WS_ENDPOINT = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"


class GeminiLiveSTT:
    """Real-time Speech-to-Text engine powered by Google Gemini Live API (gemini-3.5-transcribe-live)."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL

    def _resolve_api_key(self) -> Optional[str]:
        """Resolve API key from instance, environment variables, or ~/.config/spic/.env."""
        if self.api_key:
            return self.api_key

        for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SPIC_LLM_API_KEY"):
            val = os.environ.get(var)
            if val:
                return val

        env_file = Path.home() / ".config" / "spic" / ".env"
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SPIC_LLM_API_KEY") and v:
                        return v
            except Exception:
                pass

        # Also check ~/.config/spic/config.json
        cfg_file = Path.home() / ".config" / "spic" / "config.json"
        if cfg_file.exists():
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                key = data.get("llm", {}).get("api_key")
                if key:
                    return key
            except Exception:
                pass

        return None

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        initial_prompt: Optional[str] = None,
    ) -> Optional[str]:
        """Synchronously transcribe audio via the Gemini Live WebSocket API or REST generateContent fallback."""
        if audio.size == 0:
            return None

        api_key = self._resolve_api_key()
        if not api_key:
            logger.warning("Gemini Live API key not found. Skipping Gemini Live STT.")
            return None

        # 1. Attempt WebSocket Live API
        if websockets is not None:
            try:
                res = asyncio.run(self._async_transcribe(audio, sample_rate, api_key))
                if res:
                    return res
            except Exception as e:
                logger.debug(f"Gemini Live WebSocket error ({e}), attempting REST fallback...")

        # 2. Attempt REST Audio generateContent API
        res_rest = self._rest_transcribe(audio, sample_rate, api_key)
        if res_rest:
            return res_rest

        return None

    def _rest_transcribe(self, audio: np.ndarray, sample_rate: int, api_key: str) -> Optional[str]:
        """Transcribe audio via Google Gemini REST generateContent API with inline audio bytes."""
        import io
        import requests
        import soundfile as sf

        try:
            # Ensure float32 [-1.0, 1.0] audio is passed
            if audio.dtype != np.float32 and audio.dtype != np.float64:
                audio_float = audio.astype(np.float32) / 32768.0
            else:
                audio_float = audio

            buf = io.BytesIO()
            sf.write(buf, audio_float, sample_rate, format="WAV", subtype="PCM_16")
            b64_audio = base64.b64encode(buf.getvalue()).decode("utf-8")

            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            }
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": "audio/wav",
                                    "data": b64_audio,
                                }
                            },
                            {
                                "text": "Transcribe this audio precisely. Output ONLY the verbatim transcription with proper punctuation and capitalization. Do not include timestamps or commentary.",
                            },
                        ],
                    }
                ],
                "generationConfig": {"temperature": 0.0},
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text if text else None
        except Exception as e:
            logger.debug(f"Gemini REST transcription failed: {e}")
        return None

    async def _async_transcribe(self, audio: np.ndarray, sample_rate: int, api_key: str) -> Optional[str]:
        """Perform bidirectional streaming transcription over WebSocket."""
        uri = f"{WS_ENDPOINT}?key={api_key}"
        model_name = self.model if self.model.startswith("models/") else f"models/{self.model}"

        # Convert float32 [-1.0, 1.0] or int16 to 16-bit PCM bytes
        if audio.dtype == np.float32 or audio.dtype == np.float64:
            clipped = np.clip(audio, -1.0, 1.0)
            int16_samples = (clipped * 32767).astype(np.int16)
        else:
            int16_samples = audio.astype(np.int16)

        pcm_bytes = int16_samples.tobytes()

        async with websockets.connect(uri, max_size=10 * 1024 * 1024, close_timeout=3.0) as ws:
            # 1. Send Setup Handshake
            setup_msg = {
                "setup": {
                    "model": model_name,
                    "generationConfig": {
                        "responseModalities": ["TEXT"],
                    },
                    "inputAudioTranscription": {
                        "languageCodes": [],
                    },
                }
            }
            await ws.send(json.dumps(setup_msg))

            # Await setup confirmation
            ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            ack = json.loads(ack_raw)
            if "setupComplete" not in ack:
                logger.debug(f"Gemini Live setup response: {ack}")

            # 2. Stream audio in 100ms chunks (3200 bytes per 100ms at 16kHz 16-bit mono)
            chunk_size = int(sample_rate * 0.1 * 2)
            for i in range(0, len(pcm_bytes), chunk_size):
                chunk = pcm_bytes[i : i + chunk_size]
                b64_chunk = base64.b64encode(chunk).decode("utf-8")
                audio_msg = {
                    "realtimeInput": {
                        "mediaChunks": [
                            {
                                "mimeType": f"audio/pcm;rate={sample_rate}",
                                "data": b64_chunk,
                            }
                        ]
                    }
                }
                await ws.send(json.dumps(audio_msg))
                await asyncio.sleep(0.005)

            # Signal turn completion
            await ws.send(json.dumps({"clientContent": {"turnComplete": True}}))

            # 3. Collect Transcriptions
            collected_text: list[str] = []
            try:
                start_recv = time.time()
                while time.time() - start_recv < 6.0:
                    msg_raw = await asyncio.wait_for(ws.recv(), timeout=1.8)
                    data = json.loads(msg_raw)
                    server_content = data.get("serverContent", {})

                    if "inputTranscription" in server_content:
                        t = server_content["inputTranscription"].get("text", "")
                        if t:
                            collected_text.append(t)

                    # Model parts response
                    parts = server_content.get("modelTurn", {}).get("parts", [])
                    for p in parts:
                        text_part = p.get("text", "")
                        if text_part:
                            collected_text.append(text_part)

                    if server_content.get("turnComplete"):
                        break
            except asyncio.TimeoutError:
                pass

            result = " ".join(collected_text).strip()
            return result if result else None
