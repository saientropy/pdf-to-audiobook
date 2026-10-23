"""A stand-in voice that produces silence of a plausible length. Used by tests and dry runs."""

from __future__ import annotations

import numpy as np

WORDS_PER_SECOND = 2.6


class SilentVoice:
    name = "silent"
    sample_rate = 16000

    def synthesize(self, text: str, style: str = "") -> tuple[np.ndarray, int]:
        seconds = max(0.3, len(text.split()) / WORDS_PER_SECOND)
        return np.zeros(int(seconds * self.sample_rate), dtype=np.float32), self.sample_rate
