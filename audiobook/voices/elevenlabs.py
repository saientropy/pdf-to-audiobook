"""Cloud voice: ElevenLabs. Needs ELEVENLABS_API_KEY and a voice id (ELEVENLABS_VOICE_ID or --voice)."""

from __future__ import annotations

import os

import httpx
import numpy as np

URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class ElevenLabsVoice:
    name = "elevenlabs"
    sample_rate = 24000

    def __init__(self, voice_id: str | None = None, model: str = "eleven_v3"):
        key = os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            raise RuntimeError("set ELEVENLABS_API_KEY to use the elevenlabs voice")
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID")
        if not self.voice_id:
            raise RuntimeError("pass --voice <voice id> or set ELEVENLABS_VOICE_ID")
        self.http = httpx.Client(headers={"xi-api-key": key}, timeout=120)
        self.model = model

    def synthesize(self, text: str, style: str = "") -> tuple[np.ndarray, int]:
        # Style notes are not sent: v3 audio tags are a fixed vocabulary, and a wrong tag gets read aloud.
        r = self.http.post(URL.format(voice_id=self.voice_id), params={"output_format": "pcm_24000"},
                           json={"text": text, "model_id": self.model})
        r.raise_for_status()
        pcm = np.frombuffer(r.content, dtype="<i2").astype(np.float32) / 32768.0
        return pcm, self.sample_rate
