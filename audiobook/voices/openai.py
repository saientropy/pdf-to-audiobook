"""Voices behind an OpenAI-style /v1/audio/speech endpoint.

- OpenAIVoice: OpenAI gpt-4o-mini-tts (cloud). Takes free-text delivery instructions, so the
  narrator's style notes are performed directly. Needs OPENAI_API_KEY.
- PhononVoice: Gradium Phonon (local), through the OpenAI-compatible server in Gradium's repo.
  Start the server with the Apache-2.0 phonon-31m-en model, then point PHONON_URL at it.
"""

from __future__ import annotations

import io
import os

import httpx
import numpy as np
import soundfile as sf

BASE_INSTRUCTIONS = ("You are narrating an audiobook of a document to someone reading along. "
                     "Warm, clear, engaged, never rushed.")


class OpenAICompatibleVoice:
    name = "openai-compatible"
    sample_rate = 24000

    def __init__(self, base_url: str, model: str, voice: str, api_key: str | None = None,
                 send_instructions: bool = True):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=120)
        self.model = model
        self.voice = voice
        self.send_instructions = send_instructions

    def synthesize(self, text: str, style: str = "") -> tuple[np.ndarray, int]:
        body = {"model": self.model, "voice": self.voice, "input": text, "response_format": "wav"}
        if self.send_instructions:
            body["instructions"] = BASE_INSTRUCTIONS + (f" Delivery for this line: {style}." if style else "")
        r = self.http.post("/audio/speech", json=body)
        r.raise_for_status()
        audio, sr = sf.read(io.BytesIO(r.content), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio, sr


class OpenAIVoice(OpenAICompatibleVoice):
    name = "openai"

    def __init__(self, voice: str = "coral", model: str = "gpt-4o-mini-tts"):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("set OPENAI_API_KEY to use the openai voice")
        super().__init__("https://api.openai.com/v1", model, voice, api_key=key)


class PhononVoice(OpenAICompatibleVoice):
    name = "phonon"

    def __init__(self, voice: str = "default", model: str = "phonon-31m-en"):
        url = os.environ.get("PHONON_URL", "http://localhost:8000/v1")
        # Phonon takes no free-text instructions; style notes are dropped.
        super().__init__(url, model, voice, send_instructions=False)
