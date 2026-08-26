"""Voice Activity Detection (VAD) and silence analysis."""

from __future__ import annotations

import math
import numpy as np


class VoiceActivityDetector:
    """Detects voice activity using adaptive energy threshold and spectral analysis."""

    def __init__(self, energy_threshold: float = 0.015, sample_rate: int = 16000):
        self.energy_threshold = energy_threshold
        self.sample_rate = sample_rate
        self.noise_floor = energy_threshold * 0.5
        self.alpha = 0.95  # Exponential moving average smoothing for noise floor

    def compute_rms(self, audio_chunk: np.ndarray) -> float:
        """Compute the Root Mean Square (RMS) energy of an audio chunk."""
        if audio_chunk.size == 0:
            return 0.0
        
        # Ensure float32 format in [-1.0, 1.0]
        if audio_chunk.dtype == np.int16:
            samples = audio_chunk.astype(np.float32) / 32768.0
        else:
            samples = audio_chunk.astype(np.float32)
            
        mean_sq = np.mean(samples ** 2)
        if mean_sq <= 0:
            return 0.0
        return float(np.sqrt(mean_sq))

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """Return True if the chunk contains significant speech energy."""
        rms = self.compute_rms(audio_chunk)
        
        # Adaptive noise floor tracking during low-energy periods
        if rms < self.energy_threshold:
            self.noise_floor = self.alpha * self.noise_floor + (1 - self.alpha) * rms
            return False
            
        return rms > max(self.energy_threshold, self.noise_floor * 2.2)

    def trim_silence(self, audio: np.ndarray, frame_length_ms: int = 30) -> np.ndarray:
        """Trim leading and trailing silence from recorded audio."""
        if audio.size == 0:
            return audio
            
        frame_size = int(self.sample_rate * (frame_length_ms / 1000.0))
        num_frames = len(audio) // frame_size
        
        if num_frames == 0:
            return audio
            
        is_speech_frames = []
        for i in range(num_frames):
            frame = audio[i * frame_size:(i + 1) * frame_size]
            is_speech_frames.append(self.is_speech(frame))
            
        # Find first and last speech frame
        first_idx = 0
        last_idx = num_frames - 1
        
        for idx, has_speech in enumerate(is_speech_frames):
            if has_speech:
                first_idx = max(0, idx - 2)  # Include a 60ms pre-buffer
                break
                
        for idx in range(num_frames - 1, -1, -1):
            if is_speech_frames[idx]:
                last_idx = min(num_frames - 1, idx + 2)  # Include a 60ms post-buffer
                break
                
        start_sample = first_idx * frame_size
        end_sample = (last_idx + 1) * frame_size
        return audio[start_sample:end_sample]
