"""Audio preprocessing and enhancement for speech clarity."""

from __future__ import annotations

import numpy as np


class AudioEnhancer:
    """Provides lightweight audio filtering, DC offset removal, and volume normalization."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate

    def enhance(self, audio: np.ndarray) -> np.ndarray:
        """Apply full enhancement pipeline to float32 audio numpy array."""
        if audio.size == 0:
            return audio

        # 1. Ensure float32 format
        if audio.dtype == np.int16:
            samples = audio.astype(np.float32) / 32768.0
        else:
            samples = audio.astype(np.float32).copy()

        # 2. Remove DC offset
        samples = samples - np.mean(samples)

        # 3. Simple High-Pass Filter (~80Hz) to remove fan hum & low rumbles
        samples = self._high_pass_filter(samples, cutoff=80.0)

        # 4. Soft Noise Gating
        samples = self._noise_gate(samples, threshold=0.005)

        # 5. Peak Normalization to -1.0 dB target
        max_val = np.max(np.abs(samples))
        if max_val > 1e-4:
            target_peak = 0.89  # ~ -1 dB
            samples = (samples / max_val) * target_peak

        return samples

    def _high_pass_filter(self, data: np.ndarray, cutoff: float = 80.0) -> np.ndarray:
        """First-order IIR high-pass filter."""
        rc = 1.0 / (2.0 * np.pi * cutoff)
        dt = 1.0 / self.sample_rate
        alpha = rc / (rc + dt)

        filtered = np.zeros_like(data)
        if len(data) > 0:
            filtered[0] = data[0]
            for i in range(1, len(data)):
                filtered[i] = alpha * (filtered[i - 1] + data[i] - data[i - 1])
        return filtered

    def _noise_gate(self, data: np.ndarray, threshold: float = 0.005) -> np.ndarray:
        """Attenuate samples below noise threshold."""
        mask = np.abs(data) < threshold
        data[mask] *= 0.1  # Attenuate by 20dB instead of hard clipping
        return data
