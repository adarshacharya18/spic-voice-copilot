"""Speech-to-Text inference engine leveraging faster-whisper (CTranslate2)."""

from __future__ import annotations

import io
import logging
import time
from typing import Optional
import numpy as np
import soundfile as sf

from spic.config import STTConfig

logger = logging.getLogger("spic.stt.engine")


class STTEngine:
    """Local Speech-to-Text engine optimized for CPU / int8 quantization."""

    def __init__(self, config: STTConfig):
        self.config = config
        self._model = None

    def _get_model(self):
        """Lazy load the Whisper model into RAM."""
        if self._model is None:
            import os
            from faster_whisper import WhisperModel

            # Use at most 2 CPU threads so background STT never starves active desktop applications
            threads = max(1, min(2, (os.cpu_count() or 4) // 2))

            logger.info(
                f"Loading local STT model '{self.config.model_size}' "
                f"on {self.config.device} ({self.config.compute_type}, threads={threads})..."
            )

            start_t = time.time()
            self._model = WhisperModel(
                self.config.model_size,
                device=self.config.device,
                compute_type=self.config.compute_type,
                cpu_threads=threads,
            )
            logger.info(f"Model loaded in {time.time() - start_t:.2f}s (threads={threads}).")
        return self._model

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe a 16kHz float32 audio array to text."""
        if audio.size == 0:
            return ""

        # Audio duration check
        duration_s = len(audio) / sample_rate
        if duration_s < 0.2:  # Less than 200ms is likely a click or cough
            return ""

        logger.debug(f"Transcribing {duration_s:.2f}s of audio...")
        start_t = time.time()

        model = self._get_model()

        # faster-whisper accepts numpy float32 directly
        segments, info = model.transcribe(
            audio,
            beam_size=1,  # Greedy search for fastest CPU response
            language=self.config.language,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
        )

        text_parts = [segment.text.strip() for segment in segments]
        transcription = " ".join(part for part in text_parts if part).strip()

        elapsed = time.time() - start_t
        logger.info(f"Transcription complete in {elapsed:.2f}s (Audio: {duration_s:.1f}s): '{transcription}'")
        return transcription
