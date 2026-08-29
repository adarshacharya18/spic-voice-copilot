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

        keys_caps = parse_hotkey_combination("<CapsLock>")
        self.assertEqual(len(keys_caps), 1)

        keys_right_alt = parse_hotkey_combination("<RightAlt>")
        self.assertEqual(len(keys_right_alt), 1)

        keys_right_ctrl = parse_hotkey_combination("<RightControl>")
        self.assertEqual(len(keys_right_ctrl), 1)

        keys_f8 = parse_hotkey_combination("<F8>")
        self.assertEqual(len(keys_f8), 1)

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
        # Verify chunks were received and injected
        self.assertGreaterEqual(len(injected_chunks), 2)
        worker.stop(wait=True)

        self.assertEqual(len(injected_chunks), 3)
        self.assertEqual(injected_chunks[0], "Hello world")
        self.assertEqual(injected_chunks[1], " This is a test")
        self.assertEqual(injected_chunks[2], ", and more text")

    def test_hold_activation_timer(self):
        """Verify that micro-taps are cancelled and intentional holds trigger on_hold_start."""
        start_calls = []
        stop_calls = []

        listener = GlobalKeyHoldListener(
            binding="<RightControl>",
            on_hold_start=lambda: start_calls.append(1),
            on_hold_stop=lambda: stop_calls.append(1),
            hold_delay_ms=100,  # 100ms test delay
        )

        # 1. Simulate accidental quick tap (key down -> key up in 30ms)
        listener._on_key_match_start()
        time.sleep(0.03)
        listener._on_key_match_stop()
        time.sleep(0.12)

        # Timer was cancelled, so 0 start calls
        self.assertEqual(len(start_calls), 0)
        self.assertEqual(len(stop_calls), 0)

        # 2. Simulate intentional hold (key down -> hold 150ms -> key up)
        listener._on_key_match_start()
        time.sleep(0.15)
        self.assertEqual(len(start_calls), 1)

        listener._on_key_match_stop()
        time.sleep(0.05)
        self.assertEqual(len(stop_calls), 1)
        listener.stop()

    def test_activity_termination_watcher(self):
        """Verify that user activity (key press or mouse move) triggers instant termination."""
        from spic.shortcuts import ActivityTerminationWatcher

        triggered = []
        watcher = ActivityTerminationWatcher(
            on_activity=lambda: triggered.append(1),
            grace_period_seconds=0.05,
            mouse_threshold_px=10.0,
        )
        watcher.start()

        # 1. Action within grace period is ignored
        watcher._on_key_press("a")
        time.sleep(0.02)
        self.assertEqual(len(triggered), 0)

        # 2. Wait past grace period
        time.sleep(0.06)

        # 3. Small mouse jitter (< 10px) is ignored
        watcher._on_mouse_move(100, 100)
        watcher._on_mouse_move(103, 103)
        self.assertEqual(len(triggered), 0)

        # 4. Large intentional mouse move (> 10px) triggers!
        watcher._on_mouse_move(115, 115)
        time.sleep(0.02)
        self.assertEqual(len(triggered), 1)

        watcher.stop()


if __name__ == "__main__":
    unittest.main()
