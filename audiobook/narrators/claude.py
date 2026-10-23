"""The narrator brain: Claude reads each page (image + extracted blocks) and writes the script.

Pages are sent a few at a time. Between windows we carry a short running summary of the document
and a glossary of terms already explained, so a long book stays consistent without resending it.
"""

from __future__ import annotations

import base64
import json
import sys
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from ..extract import render_page_png
from ..model import Block, BlockKind, Document, Mode, Script, Segment, SegmentKind
from ..speech_text import clean_prose

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
You are the narrator of an audiobook made from a PDF. The listener has the PDF open and is reading \
along while you speak, so your words are synced to positions on the page.

You receive a few pages at a time: an image of each page and the text blocks a parser extracted \
from it, each with an id and a guessed kind (heading, paragraph, equation, figure, table, code, \
footnote, references). The parser can be wrong about kinds, reading order and symbols; trust the \
page image when they disagree.

Write the script for these pages as a list of segments:
- "heading": a section title. Say it the way a narrator announces a chapter, without page furniture.
- "read": the document's own words, cleaned up for listening. Keep the author's wording; do not \
summarise or paraphrase prose. Drop citation markers like [12] or (Smith et al., 2020) unless the \
name is part of the sentence. Drop footnote markers. Expand abbreviations, symbols, units and \
numbers into what a person would say ("Fig. 3" -> "Figure 3", "5 km" -> "five kilometres", \
"x_i" -> "x sub i"). Speak formulas in natural spoken maths, not symbol by symbol.
- "aside": your own words as the narrator: explanations, descriptions of figures, takeaways of \
tables, what code does, recaps. Asides must be clearly your voice ("This equation says...", \
"In this figure..."), never presented as the author's words, and must be accurate to the page. \
Do not invent results that are not on the page.
- "pause": a beat of silence (text empty) between major sections.

For every segment, set "source" to the ids of the blocks it reads or talks about (an aside about \
an equation points at that equation's block), so the reader can highlight them. Cover the pages \
in reading order. Skip running headers, footers, page numbers and anything purely decorative. \
Split long paragraphs into several "read" segments of a few sentences each.

Set "style" to a short delivery note for the voice actor, e.g. "neutral", "warm, curious", \
"slower, stress the result", "quiet aside". Leave it empty when neutral.

Write for the ear: short sentences in asides, no markdown, no lists, no symbols, no URLs read out.

Also return:
- "summary": an updated running summary of the whole document so far, at most 120 words, so \
you can stay consistent on the next pages.
- "glossary": terms you defined or symbols you explained on these pages (term + one-line meaning).
"""

MODE_PROMPTS = {
    Mode.READ: """\
Mode: READ. A clean, faithful reading. No commentary. Read formulas in natural spoken maths. For a \
figure or table, one short aside naming it and what it shows, taken from its caption. For code, \
one short aside saying a code listing is here and what it is for. Skip footnotes. When the \
references or bibliography start, one aside saying they are skipped, then skip them.""",
    Mode.EXPLAIN: """\
Mode: EXPLAIN. Read the text faithfully, and add short asides where a listener would otherwise be \
lost:
- Display equations: read it in spoken maths, then an aside explaining what each part is, what \
the equation says in plain words, and why it matters here. Two to five sentences.
- Inline maths and symbols: gloss a symbol briefly the first time it appears (check the glossary).
- Figures: look at the image and describe what is plotted or drawn and the takeaway, in two to \
four sentences. Mention axes only when that helps.
- Tables: the key takeaway and the most important numbers, never cell by cell.
- Code: what it does and how, in a sentence or two. Do not read code aloud.
- Footnotes: read as a quiet aside where they are referenced, only if they add something.
- References and bibliography: one aside saying they are skipped, then skip them.""",
    Mode.TUTOR: """\
Mode: TUTOR. Everything in EXPLAIN mode, plus:
- Define jargon and acronyms in an aside the first time they appear (check the glossary first).
- At the end of each section, a short recap aside: what the section established, in two or three \
sentences, connecting it to what came before.
- You may add one short intuition or analogy for a hard idea, clearly framed as yours.""",
}


class SegmentOut(BaseModel):
    kind: Literal["heading", "read", "aside", "pause"]
    text: str
    source: list[str] = Field(default_factory=list)
    style: str = ""


class Term(BaseModel):
    term: str
    meaning: str


class WindowOut(BaseModel):
    segments: list[SegmentOut]
    summary: str
    glossary: list[Term] = Field(default_factory=list)


class NarratorRefused(RuntimeError):
    pass


class ClaudeNarrator:
    def __init__(self, model: str = DEFAULT_MODEL, pages_per_call: int = 2, effort: str = "high",
                 dpi: int = 110, client: anthropic.Anthropic | None = None, log=sys.stderr):
        self.model = model
        self.pages_per_call = pages_per_call
        self.effort = effort
        self.dpi = dpi
        self.client = client or anthropic.Anthropic()
        self.log = log

    def narrate(self, doc: Document, mode: Mode = Mode.EXPLAIN) -> Script:
        summary = ""
        glossary: dict[str, str] = {}
        segments: list[Segment] = []
        for start in range(0, doc.page_count, self.pages_per_call):
            pages = list(range(start, min(start + self.pages_per_call, doc.page_count)))
            blocks = [b for b in doc.blocks if b.page in pages]
            if not blocks:
                continue
            print(f"  narrating pages {pages[0] + 1}-{pages[-1] + 1} of {doc.page_count}", file=self.log)
            out = self._call(doc, pages, blocks, mode, summary, glossary, segments[-1:] if segments else [])
            segments.extend(_to_segments(out.segments, blocks))
            summary = out.summary
            glossary.update({t.term: t.meaning for t in out.glossary})
        return Script(title=doc.title, mode=mode, segments=segments)

    def _call(self, doc: Document, pages: list[int], blocks: list[Block], mode: Mode, summary: str,
              glossary: dict[str, str], previous: list[Segment]) -> WindowOut:
        content: list[dict] = []
        for p in pages:
            png = render_page_png(doc.path, p, dpi=self.dpi)
            content.append({"type": "text", "text": f"Page {p + 1} of {doc.page_count}:"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                        "data": base64.standard_b64encode(png).decode()}})
        extracted = [{"id": b.id, "page": b.page + 1, "kind": b.kind.value, "text": b.text} for b in blocks]
        context = {
            "document_title": doc.title,
            "summary_so_far": summary or "(this is the start of the document)",
            "glossary_so_far": glossary,
            "last_segment_spoken": previous[0].text if previous else None,
        }
        content.append({"type": "text", "text": (
            f"Context:\n{json.dumps(context, ensure_ascii=False, indent=1)}\n\n"
            f"Extracted blocks for pages {pages[0] + 1}-{pages[-1] + 1}:\n"
            f"{json.dumps(extracted, ensure_ascii=False, indent=1)}\n\n"
            "Write the narration segments for these pages."
        )})

        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=[{"type": "text", "text": f"{SYSTEM_PROMPT}\n{MODE_PROMPTS[mode]}",
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            output_format=WindowOut,
            output_config={"effort": self.effort},
            thinking={"type": "adaptive"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise NarratorRefused(f"model declined pages {pages[0] + 1}-{pages[-1] + 1}: {response.stop_details}")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise RuntimeError(f"narration for pages {pages[0] + 1}-{pages[-1] + 1} was cut off; "
                               "try a smaller --pages-per-call")
        return response.parsed_output


def _to_segments(raw: list[SegmentOut], blocks: list[Block]) -> list[Segment]:
    """Validate model output: keep only known block ids, and run the speech-text safety net."""
    known = {b.id for b in blocks}
    out = []
    for s in raw:
        kind = SegmentKind(s.kind)
        source = [i for i in s.source if i in known]
        if kind == SegmentKind.PAUSE:
            out.append(Segment(kind, "", source, s.style, pause=0.8))
            continue
        text = clean_prose(s.text) if kind == SegmentKind.READ else s.text.strip()
        if text:
            out.append(Segment(kind, text, source, s.style))
    return out


def uncovered_blocks(doc: Document, script: Script) -> list[Block]:
    """Prose blocks the narrator never pointed at; useful as a sanity check on long documents."""
    covered = {i for s in script.segments for i in s.source}
    return [b for b in doc.blocks if b.kind in (BlockKind.PARAGRAPH, BlockKind.HEADING) and b.id not in covered]
