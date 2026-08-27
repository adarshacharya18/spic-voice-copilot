"""Asynchronous Streaming STT Worker with rolling prompt context and seamless on-the-go injection."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Optional
import numpy as np

from spic.stt.engine import STTEngine
from spic.interpreter.rule_cleaner import RuleCleaner
from spic.injector.input_injector import InputInjector

logger = logging.getLogger("spic.stt.stream_worker")


class StreamTranscriptionWorker:
    """Consumes audio slices, transcribes them in parallel, and injects text into the active app on the fly."""

    def __init__(
        self,
        stt: STTEngine,
        injector: InputInjector,
        sample_rate: int = 16000,
        smart_spacing: bool = True,
        on_chunk_injected: Optional[Callable[[str], None]] = None,
        on_stream_finished: Optional[Callable[[], None]] = None,
    ):
        self.stt = stt
        self.injector = injector
        self.sample_rate = sample_rate
        self.smart_spacing = smart_spacing
        self.on_chunk_injected = on_chunk_injected
        self.on_stream_finished = on_stream_finished

        self.cleaner = RuleCleaner()
        self._queue: queue.Queue[tuple[np.ndarray, bool]] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Session state
        self._chunks_injected_count = 0
        self._rolling_context = ""
        self._last_char = ""

    def start(self) -> None:
        """Start the worker thread."""
        self._running = True
        self._chunks_injected_count = 0
        self._rolling_context = ""
        self._last_char = ""
        # Clear any stale queue items
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                break

        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def enqueue_chunk(self, audio: np.ndarray, is_final: bool = False) -> None:
        """Push an audio slice to the async transcription queue."""
        self._queue.put((audio, is_final))

    def stop(self, wait: bool = True) -> None:
        """Signal the worker to finish processing remaining chunks."""
        self._running = False
        if wait and self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def _worker_loop(self) -> None:
        """Continuously process enqueued audio slices."""
        while self._running or not self._queue.empty():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            audio, is_final = item

            if audio.size > 0:
                self._process_chunk(audio)

            self._queue.task_done()

            if is_final:
                has_injected = self._chunks_injected_count > 0
                logger.info(f"Stream session finalized (Total chunks injected: {self._chunks_injected_count}).")
                if self.on_stream_finished:
                    try:
                        self.on_stream_finished(has_injected)
                    except TypeError:
                        try:
                            self.on_stream_finished()
                        except Exception:
                            pass
                    except Exception as e:
                        logger.error(f"Error in on_stream_finished callback: {e}")
                break

    def _process_chunk(self, audio: np.ndarray) -> None:
        """Transcribe and inject a single audio slice on the fly."""
        try:
            raw_text = self.stt.transcribe(
                audio,
                sample_rate=self.sample_rate,
                initial_prompt=self._rolling_context[-200:] if self._rolling_context else None,
            )

            if not raw_text or not raw_text.strip():
                return

            clean_text = self.cleaner.clean(raw_text).strip()
            if not clean_text:
                return

            # Apply smart inter-chunk spacing
            formatted_text = clean_text
            if self.smart_spacing and self._chunks_injected_count > 0:
                # If chunk starts with alphanumeric and previous chunk didn't end with space
                if clean_text[0].isalnum() and not self._last_char.isspace():
                    formatted_text = " " + clean_text

            logger.info(f"⚡ [Stream Chunk #{self._chunks_injected_count + 1}] Transcribed: '{formatted_text}'")

            # Inject text at active cursor immediately
            success, method = self.injector.inject_text(formatted_text)
            logger.debug(f"Stream chunk injection status: {success} via {method}")

            self._chunks_injected_count += 1
            self._rolling_context += " " + clean_text
            self._last_char = formatted_text[-1] if formatted_text else ""

            if self.on_chunk_injected:
                try:
                    self.on_chunk_injected(formatted_text)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Failed to process stream chunk: {e}", exc_info=True)
