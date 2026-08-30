"""Unit tests for Gemini Live STT Engine and fallback integration."""

import unittest
from unittest.mock import patch, MagicMock
import numpy as np

from spic.config import STTConfig
from spic.stt.engine import STTEngine
from spic.stt.gemini_live import GeminiLiveSTT


class TestGeminiLiveSTT(unittest.TestCase):
    """Test suite for Gemini Live WebSocket STT and fallback handling."""

    def test_gemini_live_missing_key_graceful_fallback(self):
        """Verify that GeminiLiveSTT returns None without error when no key is found."""
        engine = GeminiLiveSTT(api_key=None)
        with patch.object(engine, "_resolve_api_key", return_value=None):
            audio = np.zeros(16000, dtype=np.float32)
            res = engine.transcribe(audio)
            self.assertIsNone(res)

    def test_stt_engine_gemini_live_fallback_to_whisper(self):
        """Verify that STTEngine falls back to local Whisper when Gemini Live returns None."""
        config = STTConfig(engine="gemini-live")
        stt = STTEngine(config)

        # Mock GeminiLiveSTT to return None
        stt._gemini_live.transcribe = MagicMock(return_value=None)

        # Mock Whisper model
        mock_segment = MagicMock()
        mock_segment.text = "Hello from local Whisper fallback"
        mock_whisper = MagicMock()
        mock_whisper.transcribe.return_value = ([mock_segment], None)
        stt._model = mock_whisper

        audio = np.zeros(16000, dtype=np.float32)
        result = stt.transcribe(audio)

        self.assertEqual(result, "Hello from local Whisper fallback")
        stt._gemini_live.transcribe.assert_called_once()
        mock_whisper.transcribe.assert_called_once()

    def test_stt_engine_gemini_live_success(self):
        """Verify that STTEngine returns Gemini Live output when successful."""
        config = STTConfig(engine="gemini-live")
        stt = STTEngine(config)

        stt._gemini_live.transcribe = MagicMock(return_value="Live transcribed speech via Gemini")

        audio = np.zeros(16000, dtype=np.float32)
        result = stt.transcribe(audio)

        self.assertEqual(result, "Live transcribed speech via Gemini")
        stt._gemini_live.transcribe.assert_called_once()


if __name__ == "__main__":
    unittest.main()
