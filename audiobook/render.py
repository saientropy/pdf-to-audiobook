"""Step 4: perform a script with a voice engine and write chapter audio plus a sync map.

Output folder:
    01-introduction.mp3, 02-method.mp3, ...   one file per chapter (a chapter starts at each heading)
    book.json                                  chapters, and every segment and sentence with its
                                               start/end time and where it sits on the page
    script.json                                the narration script that was performed
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from .model import Document, Script, Segment, SegmentKind
from .speech_text import split_sentences
from .voices import VoiceEngine

GAP_SENTENCE = 0.18
GAP_SEGMENT = 0.4
GAP_AFTER_HEADING = 0.7


@dataclass
class Chapter:
    title: str
    segments: list[tuple[int, Segment]] = field(default_factory=list)  # (index in script, segment)


def split_chapters(script: Script) -> list[Chapter]:
    chapters: list[Chapter] = []
    for i, seg in enumerate(script.segments):
        if seg.kind == SegmentKind.HEADING or not chapters:
            chapters.append(Chapter(seg.text.rstrip(".") if seg.kind == SegmentKind.HEADING else script.title))
        chapters[-1].segments.append((i, seg))
    return chapters


def render(doc: Document, script: Script, voice: VoiceEngine, out_dir: Path, audio_format: str = "mp3",
           log=sys.stderr) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / ".cache"
    cache.mkdir(exist_ok=True)
    if audio_format != "wav" and not shutil.which("ffmpeg"):
        print("  ffmpeg not found; writing .wav instead", file=log)
        audio_format = "wav"

    book = {"title": script.title, "mode": script.mode.value, "voice": voice.name, "source_pdf": doc.path,
            "page_sizes": doc.page_sizes, "chapters": [], "segments": []}
    book_time = 0.0
    sr = voice.sample_rate
    chapters = split_chapters(script)

    for n, chapter in enumerate(chapters, start=1):
        print(f"  [{n}/{len(chapters)}] {chapter.title}", file=log)
        pieces: list[np.ndarray] = []
        t = 0.0
        for index, seg in chapter.segments:
            entry = _segment_entry(doc, index, seg)
            entry["chapter"] = n - 1
            entry["start"] = round(book_time + t, 3)
            if seg.kind == SegmentKind.PAUSE:
                pieces.append(_silence(seg.pause or GAP_SEGMENT, sr))
                t += seg.pause or GAP_SEGMENT
            else:
                sentences = [seg.text] if seg.kind == SegmentKind.HEADING else split_sentences(seg.text) or [seg.text]
                for sentence in sentences:
                    audio, sr = _synthesize_cached(voice, sentence, seg.style, cache)
                    dur = len(audio) / sr
                    entry["sentences"].append({"text": sentence, "start": round(book_time + t, 3),
                                               "end": round(book_time + t + dur, 3)})
                    pieces += [audio, _silence(GAP_SENTENCE, sr)]
                    t += dur + GAP_SENTENCE
                gap = GAP_AFTER_HEADING if seg.kind == SegmentKind.HEADING else GAP_SEGMENT
                pieces.append(_silence(gap, sr))
                t += gap
            entry["end"] = round(book_time + t, 3)
            book["segments"].append(entry)

        filename = f"{n:02d}-{_slug(chapter.title)}.{audio_format}"
        _write_audio(np.concatenate(pieces) if pieces else _silence(0.1, sr), sr, out_dir / filename)
        book["chapters"].append({"title": chapter.title, "file": filename, "start": round(book_time, 3),
                                 "duration": round(t, 3)})
        book_time += t

    book["duration"] = round(book_time, 3)
    (out_dir / "book.json").write_text(json.dumps(book, indent=2, ensure_ascii=False), encoding="utf-8")
    script.save(out_dir / "script.json")
    return book


def _segment_entry(doc: Document, index: int, seg: Segment) -> dict:
    blocks = [b for b in (doc.block(i) for i in seg.source) if b]
    return {
        "id": index,
        "kind": seg.kind.value,
        "text": seg.text,
        "style": seg.style,
        "source": seg.source,
        # Where to highlight while this plays. An aside highlights the thing it explains.
        "anchors": [{"page": b.page, "bbox": list(b.bbox)} for b in blocks],
        "sentences": [],
    }


def _synthesize_cached(voice: VoiceEngine, text: str, style: str, cache: Path) -> tuple[np.ndarray, int]:
    key = hashlib.sha256(json.dumps([voice.name, getattr(voice, "voice", ""), text, style]).encode()).hexdigest()[:24]
    path = cache / f"{key}.wav"
    if path.exists():
        audio, sr = sf.read(path, dtype="float32")
        return audio, sr
    audio, sr = voice.synthesize(text, style)
    sf.write(path, audio, sr)
    return audio, sr


def _silence(seconds: float, sr: int) -> np.ndarray:
    return np.zeros(int(seconds * sr), dtype=np.float32)


def _write_audio(audio: np.ndarray, sr: int, path: Path) -> None:
    if path.suffix == ".wav":
        sf.write(path, audio, sr)
        return
    wav = path.with_suffix(".wav")
    sf.write(wav, audio, sr)
    codec = ["-c:a", "aac", "-b:a", "96k"] if path.suffix == ".m4a" else ["-b:a", "96k"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), *codec, str(path)], check=True)
    wav.unlink()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "chapter"
