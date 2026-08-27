"""Unit tests for On-the-GO continuous stream dictation pipeline."""

import unittest
import time
import numpy as np

from spic.config import SpicConfig, StreamConfig
from spic.shortcuts import parse_hotkey_combination, GlobalKeyHoldListener
from spic.stt.stream_worker import StreamTranscriptionWorker


class TestStreamDictation(unittest.TestCase):
    """Test suite for continuous stream dictation worker and key combination parser."""

    def test_parse_hotkey_combination(self):
        """Verify parsing of various shortcut string formats."""
        keys_ctrl_m = parse_hotkey_combination("<Control>m")
        self.assertGreaterEqual(len(keys_ctrl_m), 2)

        keys_ctrl_alt_space = parse_hotkey_combination("<Control><Alt>space")
        self.assertGreaterEqual(len(keys_ctrl_alt_space), 3)

    def test_stream_worker_smart_spacing(self):
        """Verify smart spacing between sequential stream chunks."""
        injected_chunks = []

        class MockSTT:
            def __init__(self):
                self.call_count = 0
                self.responses = ["Hello world.", "this is a test", ", and more text."]

            def transcribe(self, audio, sample_rate=16000, initial_prompt=None):
                resp = self.responses[min(self.call_count, len(self.responses) - 1)]
                self.call_count += 1
                return resp

        class MockInjector:
            def inject_text(self, text):
                injected_chunks.append(text)
                return True, "mock"

        stt = MockSTT()
        injector = MockInjector()
        worker = StreamTranscriptionWorker(
            stt=stt,
            injector=injector,
            smart_spacing=True,
        )
        worker.start()

        dummy_audio = np.zeros(16000, dtype=np.float32)

        # Chunk 1
        worker.enqueue_chunk(dummy_audio, is_final=False)
        time.sleep(0.15)

        # Chunk 2 (starts with alphanumeric, should have prepended space)
        worker.enqueue_chunk(dummy_audio, is_final=False)
        time.sleep(0.15)

        # Chunk 3 (starts with comma, should NOT have prepended space)
        worker.enqueue_chunk(dummy_audio, is_final=True)
        time.sleep(0.2)
        worker.stop(wait=True)

        self.assertEqual(len(injected_chunks), 3)
        self.assertEqual(injected_chunks[0], "Hello world")
        self.assertEqual(injected_chunks[1], " This is a test")
        self.assertEqual(injected_chunks[2], ", and more text")


if __name__ == "__main__":
    unittest.main()
