"""Offline narrator: a clean, faithful Read-mode script built from rules alone."""

from __future__ import annotations

import re

from ..model import Block, BlockKind, Document, Mode, Script, Segment, SegmentKind
from ..speech_text import clean_prose, speak_math

_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$")
_LABEL = re.compile(r"^((?:fig\.?|figure|table|tab\.)\s*\d+[a-z]?)\s*[:.|—–-]\s*(.*)", re.IGNORECASE | re.DOTALL)


class RuleNarrator:
    def narrate(self, doc: Document, mode: Mode = Mode.READ) -> Script:
        segments: list[Segment] = []
        announced_refs = False
        for b in doc.blocks:
            if b.kind == BlockKind.REFERENCES:
                if not announced_refs:
                    segments.append(Segment(SegmentKind.ASIDE, "The list of references is skipped.", [b.id],
                                            "quiet aside"))
                    announced_refs = True
                continue
            seg = self._segment(b)
            if seg:
                if seg.kind == SegmentKind.HEADING and segments:
                    segments.append(Segment(SegmentKind.PAUSE, "", [], pause=0.8))
                segments.append(seg)
        return Script(title=doc.title, mode=Mode.READ, segments=segments)

    def _segment(self, b: Block) -> Segment | None:
        if b.kind == BlockKind.HEADING:
            m = _NUMBERED_HEADING.match(b.text)
            text = f"Section {m.group(1)}. {m.group(2)}." if m else f"{b.text.rstrip('.')}."
            return Segment(SegmentKind.HEADING, text, [b.id], "title")
        if b.kind == BlockKind.PARAGRAPH:
            text = clean_prose(b.text)
            return Segment(SegmentKind.READ, text, [b.id]) if text else None
        if b.kind == BlockKind.EQUATION:
            return Segment(SegmentKind.READ, f"{speak_math(b.text)}.", [b.id], "slow and clear")
        if b.kind in (BlockKind.FIGURE, BlockKind.TABLE, BlockKind.CAPTION):
            return Segment(SegmentKind.ASIDE, self._mention(b), [b.id], "quiet aside")
        if b.kind == BlockKind.CODE:
            return Segment(SegmentKind.ASIDE, "There is a code listing here.", [b.id], "quiet aside")
        return None  # footnotes are skipped in Read mode

    @staticmethod
    def _mention(b: Block) -> str:
        noun = "table" if b.kind == BlockKind.TABLE else "figure"
        caption = b.text.split("\n", 1)[0].strip()
        m = _LABEL.match(caption)
        if m:
            label = re.sub(r"(?i)^fig\.?(?=\s|\d)", "Figure", re.sub(r"(?i)^tab\.", "Table", m.group(1)))
            return clean_prose(f"{label.capitalize()}: {m.group(2).strip()}")
        return f"There is a {noun} here."
