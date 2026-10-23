"""Core data types shared by every stage of the pipeline.

    PDF -> [Block] (extract) -> Script of [Segment] (narrator) -> audio + SyncMap (render)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class BlockKind(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    EQUATION = "equation"
    FIGURE = "figure"  # a figure region; text is its caption, if any
    TABLE = "table"
    CODE = "code"
    FOOTNOTE = "footnote"
    REFERENCES = "references"  # bibliography entries
    CAPTION = "caption"  # caption not yet attached to a figure/table


class SegmentKind(str, Enum):
    HEADING = "heading"  # starts a chapter
    READ = "read"  # the document's own words, cleaned up for speech
    ASIDE = "aside"  # the narrator's commentary (explanations, descriptions, recaps)
    PAUSE = "pause"


class Mode(str, Enum):
    READ = "read"
    EXPLAIN = "explain"
    TUTOR = "tutor"


BBox = tuple[float, float, float, float]


@dataclass
class Block:
    id: str  # "p{page}-b{n}", stable within one extraction
    page: int  # 0-based
    bbox: BBox
    kind: BlockKind
    text: str
    level: int = 0  # heading level (1 = top), 0 otherwise


@dataclass
class Document:
    path: str
    title: str
    page_count: int
    page_sizes: list[tuple[float, float]]
    blocks: list[Block]

    def blocks_on(self, page: int) -> list[Block]:
        return [b for b in self.blocks if b.page == page]

    def block(self, block_id: str) -> Block | None:
        return next((b for b in self.blocks if b.id == block_id), None)


@dataclass
class Segment:
    kind: SegmentKind
    text: str  # exactly what will be spoken
    source: list[str] = field(default_factory=list)  # Block ids this segment comes from or is about
    style: str = ""  # delivery hint for steerable voices, e.g. "quiet aside"
    pause: float = 0.0  # seconds; used by PAUSE segments


@dataclass
class Script:
    title: str
    mode: Mode
    segments: list[Segment]

    def to_json(self) -> str:
        data = {
            "title": self.title,
            "mode": self.mode.value,
            "segments": [{**asdict(s), "kind": s.kind.value} for s in self.segments],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> Script:
        data = json.loads(text)
        segments = [Segment(**{**s, "kind": SegmentKind(s["kind"])}) for s in data["segments"]]
        return cls(title=data["title"], mode=Mode(data["mode"]), segments=segments)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Script:
        return cls.from_json(path.read_text(encoding="utf-8"))
