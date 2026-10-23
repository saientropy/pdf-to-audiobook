"""Local voice: Kokoro-82M via ONNX (Apache 2.0). Runs on CPU on any desktop; ONNX also runs on
iOS, Android and in the browser, so the same model can ship in a future app."""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

import numpy as np

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
MODEL_FILE = "kokoro-v1.0.int8.onnx"  # ~88 MB; the fp32 model is ~310 MB for a small quality gain
VOICES_FILE = "voices-v1.0.bin"

# Kokoro takes no style instructions, but speed is a lever that matches some delivery notes.
SLOW_WORDS = ("slow", "careful", "clear")


def models_dir() -> Path:
    return Path(os.environ.get("AUDIOBOOK_MODELS_DIR", Path.home() / ".cache" / "pdf-to-audiobook"))


def ensure_model_files(directory: Path | None = None) -> tuple[Path, Path]:
    directory = directory or models_dir()
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in (MODEL_FILE, VOICES_FILE):
        path = directory / name
        if not path.exists():
            print(f"  downloading {name} to {directory} (one-time)", file=sys.stderr)
            tmp = path.with_suffix(".part")
            urllib.request.urlretrieve(f"{RELEASE}/{name}", tmp)
            tmp.rename(path)
        paths.append(path)
    return paths[0], paths[1]


class KokoroVoice:
    name = "kokoro"
    sample_rate = 24000

    def __init__(self, voice: str = "af_heart", speed: float = 1.0, lang: str = "en-us"):
        from kokoro_onnx import Kokoro

        model, voices = ensure_model_files()
        self.tts = Kokoro(str(model), str(voices))
        if voice not in self.tts.get_voices():
            raise ValueError(f"unknown Kokoro voice {voice!r}; try one of {sorted(self.tts.get_voices())[:8]}...")
        self.voice = voice
        self.speed = speed
        self.lang = lang

    def synthesize(self, text: str, style: str = "") -> tuple[np.ndarray, int]:
        speed = self.speed * (0.9 if any(w in style.lower() for w in SLOW_WORDS) else 1.0)
        samples, sr = self.tts.create(text, voice=self.voice, speed=speed, lang=self.lang)
        return samples.astype(np.float32), sr
