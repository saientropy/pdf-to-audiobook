"""Step 3: voice engines perform script segments as audio.

Every engine has the same shape, so the voice can change without touching the narrator:

    engine.synthesize(text, style) -> (mono float32 samples, sample_rate)

`style` is the narrator's delivery note ("quiet aside", "slower, stress the result"). Steerable
engines use it; others ignore it.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np


class VoiceEngine(Protocol):
    name: str
    sample_rate: int

    def synthesize(self, text: str, style: str = "") -> tuple[np.ndarray, int]: ...


def get_voice(name: str, voice: str | None = None) -> VoiceEngine:
    if name == "kokoro":
        from .kokoro import KokoroVoice

        return KokoroVoice(voice=voice or "af_heart")
    if name == "openai":
        from .openai import OpenAIVoice

        return OpenAIVoice(voice=voice or "coral")
    if name == "phonon":
        from .openai import PhononVoice

        return PhononVoice(voice=voice or "default")
    if name == "elevenlabs":
        from .elevenlabs import ElevenLabsVoice

        return ElevenLabsVoice(voice_id=voice)
    if name == "silent":
        from .silent import SilentVoice

        return SilentVoice()
    raise ValueError(f"unknown voice engine {name!r} (expected kokoro, phonon, openai, elevenlabs or silent)")
