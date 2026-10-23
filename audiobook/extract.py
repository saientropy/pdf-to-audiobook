"""Step 1: turn a PDF into an ordered list of typed blocks.

Everything here is deterministic and runs locally. It does the cheap, reliable work (dropping
running headers, footers and page numbers, fixing hyphenation, finding reading order) and makes a
best guess at what each block is. The narrator sees the page images too, so these guesses only
need to be good enough to anchor and organise the script.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .model import BBox, Block, BlockKind, Document

EDGE_BAND = 0.08
FIGURE_LABEL_MARGIN = 30  # axis labels and legends sit just outside a figure's drawn lines  # top/bottom fraction of the page where running headers and footers live
MATH_CHARS = set("=+−-×·÷/^_∑Σ∏∫√∞≤≥≠≈∂∇θλμσπαβγδεωφψΔΩ∈∉⊂⊆∪∩→←↔ˆ̂ᵢⱼₖₙ₀₁₂₃")
CAPTION_RE = re.compile(r"^(fig\.?|figure|table|tab\.)\s*\d+[a-z]?\s*[:.|—–-]", re.IGNORECASE)
REFERENCES_RE = re.compile(r"^\s*(\d+\.?\s+)?(references|bibliography|works cited|literature cited)\s*$",
                           re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^\s*(page\s+)?(\d{1,4}|[ivxlcdm]{1,6})(\s+of\s+\d+)?\s*$", re.IGNORECASE)
EQ_NUMBER_RE = re.compile(r"\(\d{1,3}[a-z]?\)\s*$")
FOOTNOTE_START_RE = re.compile(r"^[\d¹²³⁴⁵⁶⁷⁸⁹⁰*†‡§]")


@dataclass
class RawBlock:
    page: int
    bbox: BBox
    text: str
    size: float
    bold: bool
    mono: bool


def extract(path: str | Path) -> Document:
    pdf = pymupdf.open(str(path))
    raws = [r for page in pdf for r in _raw_blocks(page)]
    body = _body_font_size(raws)
    sizes = [(p.rect.width, p.rect.height) for p in pdf]
    raws = _drop_running_furniture(raws, sizes, pdf.page_count)

    blocks: list[Block] = []
    for page in pdf:
        page_raws = [r for r in raws if r.page == page.number]
        blocks.extend(_page_blocks(page, page_raws, body))

    _assign_heading_levels(blocks)
    _mark_references(blocks)
    title = _title(pdf, blocks)
    return Document(path=str(path), title=title, page_count=pdf.page_count, page_sizes=sizes, blocks=blocks)


def render_page_png(path: str | Path, page: int, dpi: int = 110) -> bytes:
    with pymupdf.open(str(path)) as pdf:
        return pdf[page].get_pixmap(dpi=dpi).tobytes("png")


# --- raw text -------------------------------------------------------------------------------


def _raw_blocks(page: pymupdf.Page) -> list[RawBlock]:
    out = []
    for b in page.get_text("dict", sort=False)["blocks"]:
        if b["type"] != 0:
            continue
        lines = []
        sizes: Counter[float] = Counter()
        bold = mono = 0
        for line in b["lines"]:
            text = "".join(span["text"] for span in line["spans"])
            if text.strip():
                lines.append(text)
            for span in line["spans"]:
                n = len(span["text"].strip())
                sizes[round(span["size"], 1)] += n
                font = span["font"].lower()
                if span["flags"] & 16 or "bold" in font:
                    bold += n
                if span["flags"] & 8 or any(m in font for m in ("mono", "courier", "consol", "code")):
                    mono += n
        if not lines:
            continue
        total = max(sum(sizes.values()), 1)
        out.append(RawBlock(
            page=page.number,
            bbox=tuple(b["bbox"]),
            text=_join_lines(lines, keep_breaks=mono > total / 2),
            size=sizes.most_common(1)[0][0],
            bold=bold > total / 2,
            mono=mono > total / 2,
        ))
    return out


def _join_lines(lines: list[str], keep_breaks: bool = False) -> str:
    if keep_breaks:
        return "\n".join(l.rstrip() for l in lines)
    text = ""
    for line in (l.strip() for l in lines):
        if not text:
            text = line
        elif text.endswith("-") and line[:1].islower():
            next_word = line.split(" ", 1)[0]
            # "de-" + "vices" -> "devices", but "state-" + "of-the-art" -> "state-of-the-art"
            text = text + line if "-" in next_word else text[:-1] + line
        else:
            text += " " + line
    return re.sub(r"\s{2,}", " ", text)


def _body_font_size(raws: list[RawBlock]) -> float:
    weights: Counter[float] = Counter()
    for r in raws:
        weights[r.size] += len(r.text)
    return weights.most_common(1)[0][0] if weights else 10.0


def _furniture_key(text: str) -> str:
    return re.sub(r"\d+", "#", text.strip().lower())


def _drop_running_furniture(raws: list[RawBlock], sizes: list[tuple[float, float]], pages: int) -> list[RawBlock]:
    """Drop page numbers, and headers/footers that repeat across pages near the top or bottom edge."""

    def in_band(r: RawBlock) -> bool:
        h = sizes[r.page][1]
        return r.bbox[3] < h * EDGE_BAND + 20 or r.bbox[1] > h * (1 - EDGE_BAND) - 20

    repeats = Counter(_furniture_key(r.text) for r in raws if in_band(r))
    min_repeats = max(2, pages // 2) if pages > 1 else 99
    kept = []
    for r in raws:
        if in_band(r) and (PAGE_NUMBER_RE.match(r.text) or repeats[_furniture_key(r.text)] >= min_repeats):
            continue
        kept.append(r)
    return kept


# --- per-page classification ---------------------------------------------------------------


def _page_blocks(page: pymupdf.Page, raws: list[RawBlock], body: float) -> list[Block]:
    tables = _find_tables(page)
    figures = _find_figures(page, [t[0] for t in tables])
    items: list[tuple[BBox, BlockKind, str]] = []

    for bbox, text in tables:
        items.append((bbox, BlockKind.TABLE, text))
    for bbox in figures:
        items.append((bbox, BlockKind.FIGURE, ""))

    regions = [t[0] for t in tables] + [_grow(f, FIGURE_LABEL_MARGIN) for f in figures]
    for r in raws:
        if any(_inside(r.bbox, reg) for reg in regions):
            continue  # cell text and axis labels are represented by the table/figure block
        items.append((r.bbox, _classify(r, page, body), r.text))

    items = _attach_captions(items)
    items = _reading_order(items, page.rect.width)
    return [Block(id=f"p{page.number + 1}-b{i + 1}", page=page.number, bbox=tuple(round(v, 1) for v in bbox),
                  kind=kind, text=text) for i, (bbox, kind, text) in enumerate(items)]


def _classify(r: RawBlock, page: pymupdf.Page, body: float) -> BlockKind:
    text = r.text.strip()
    if r.mono:
        return BlockKind.CODE
    if CAPTION_RE.match(text):
        return BlockKind.CAPTION
    short = len(text) < 120 and "\n" not in text
    if short and (r.size >= body * 1.15 or (r.bold and len(text) < 80 and not text.endswith("."))):
        return BlockKind.HEADING
    if r.size < body * 0.85 and r.bbox[1] > page.rect.height * 0.75 and FOOTNOTE_START_RE.match(text):
        return BlockKind.FOOTNOTE
    if _looks_like_equation(text, r.bbox, page.rect.width):
        return BlockKind.EQUATION
    return BlockKind.PARAGRAPH


def _looks_like_equation(text: str, bbox: BBox, page_width: float) -> bool:
    if len(text) > 200:
        return False
    compact = text.replace(" ", "")
    if not compact:
        return False
    math_ratio = sum(c in MATH_CHARS for c in compact) / len(compact)
    centred = abs((bbox[0] + bbox[2]) / 2 - page_width / 2) < page_width * 0.08 and (bbox[2] - bbox[0]) < page_width * 0.7
    words = re.findall(r"[A-Za-z]{4,}", text)
    return (EQ_NUMBER_RE.search(text) is not None and centred) or (math_ratio > 0.15 and len(words) <= 3)


def _find_tables(page: pymupdf.Page) -> list[tuple[BBox, str]]:
    out = []
    try:
        found = page.find_tables()
    except Exception:  # table finder is best-effort; never fail extraction on it
        return out
    for t in found.tables:
        rows = [" | ".join(_cell_text(page, c) for c in row.cells) for row in t.rows]
        rows = [r for r in rows if r.strip(" |")]
        if len(rows) >= 2:
            out.append((tuple(t.bbox), "\n".join(rows)))
    return out


def _cell_text(page: pymupdf.Page, cell: tuple | None) -> str:
    return " ".join(page.get_textbox(cell).split()) if cell else ""


def _find_figures(page: pymupdf.Page, exclude: list[BBox]) -> list[BBox]:
    regions: list[BBox] = []
    area = page.rect.width * page.rect.height
    for info in page.get_images(full=True):
        for rect in page.get_image_rects(info[0]):
            if rect.width * rect.height > area * 0.01:
                regions.append(tuple(rect))
    try:
        clusters = page.cluster_drawings()
    except Exception:
        clusters = []
    for rect in clusters:
        bbox = tuple(rect)
        big = rect.width > 60 and rect.height > 40
        if big and not any(_overlap(bbox, ex) > 0.5 for ex in exclude):
            regions.append(bbox)
    return _merge_overlapping(regions)


def _attach_captions(items: list[tuple[BBox, BlockKind, str]]) -> list[tuple[BBox, BlockKind, str]]:
    """Fold a "Figure N: ..." / "Table N: ..." caption into the nearest figure or table block."""
    out = list(items)
    for cap in [i for i in items if i[1] == BlockKind.CAPTION]:
        is_table = cap[2].lower().startswith(("table", "tab."))
        want = BlockKind.TABLE if is_table else BlockKind.FIGURE
        targets = [i for i in out if i[1] == want]
        if not targets:
            out[out.index(cap)] = (cap[0], BlockKind.FIGURE if not is_table else BlockKind.TABLE, cap[2])
            continue
        target = min(targets, key=lambda t: _vertical_gap(cap[0], t[0]))
        if _vertical_gap(cap[0], target[0]) > 60:
            continue
        idx = out.index(target)
        text = cap[2] if not target[2] else f"{cap[2]}\n{target[2]}"
        out[idx] = (_union(target[0], cap[0]), target[1], text)
        out.remove(cap)
    return out


def _reading_order(items: list[tuple[BBox, BlockKind, str]], width: float) -> list[tuple[BBox, BlockKind, str]]:
    """Top-to-bottom, but read a two-column stretch left column first, then right column."""
    mid = width / 2
    full = [i for i in items if i[0][0] < mid - 10 and i[0][2] > mid + 10]
    narrow = [i for i in items if i not in full]
    two_column = sum(1 for i in narrow if i[0][0] >= mid - 10) >= 2 and sum(1 for i in narrow if i[0][2] <= mid + 10) >= 2
    if not two_column:
        return sorted(items, key=lambda i: (round(i[0][1]), i[0][0]))

    out: list[tuple[BBox, BlockKind, str]] = []
    pending = sorted(narrow, key=lambda i: i[0][1])
    for f in sorted(full, key=lambda i: i[0][1]) + [None]:
        cutoff = f[0][1] if f else float("inf")
        band = [i for i in pending if i[0][1] < cutoff]
        pending = [i for i in pending if i not in band]
        out += sorted(band, key=lambda i: (i[0][0] >= mid - 10, i[0][1]))
        if f:
            out.append(f)
    return out


# --- document-level passes -------------------------------------------------------------------


def _assign_heading_levels(blocks: list[Block]) -> None:
    # Heading size is not kept on Block, so rank by order of appearance of distinct texts' lengths is
    # unreliable; use a simple rule instead: numbered "1.2" style headings nest by their dots.
    for b in blocks:
        if b.kind != BlockKind.HEADING:
            continue
        m = re.match(r"^(\d+(?:\.\d+)*)\.?\s", b.text)
        b.level = m.group(1).count(".") + 1 if m else 1


def _mark_references(blocks: list[Block]) -> None:
    in_refs = False
    for b in blocks:
        if b.kind == BlockKind.HEADING:
            in_refs = bool(REFERENCES_RE.match(b.text))
            continue
        if in_refs and b.kind in (BlockKind.PARAGRAPH, BlockKind.FOOTNOTE, BlockKind.EQUATION):
            b.kind = BlockKind.REFERENCES


def _title(pdf: pymupdf.Document, blocks: list[Block]) -> str:
    meta = (pdf.metadata or {}).get("title", "").strip()
    if meta:
        return meta
    first = [b for b in blocks if b.page == 0 and b.kind == BlockKind.HEADING]
    return first[0].text if first else Path(pdf.name).stem


# --- geometry -------------------------------------------------------------------------------


def _inside(inner: BBox, outer: BBox, slack: float = 2) -> bool:
    return (inner[0] >= outer[0] - slack and inner[1] >= outer[1] - slack
            and inner[2] <= outer[2] + slack and inner[3] <= outer[3] + slack)


def _overlap(a: BBox, b: BBox) -> float:
    """Intersection area as a fraction of a's area."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    area = (a[2] - a[0]) * (a[3] - a[1])
    return (w * h) / area if w > 0 and h > 0 and area > 0 else 0.0


def _grow(a: BBox, by: float) -> BBox:
    return (a[0] - by, a[1] - by, a[2] + by, a[3] + by)


def _union(a: BBox, b: BBox) -> BBox:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _vertical_gap(a: BBox, b: BBox) -> float:
    if a[3] < b[1]:
        return b[1] - a[3]
    if b[3] < a[1]:
        return a[1] - b[3]
    return 0.0


def _merge_overlapping(boxes: list[BBox]) -> list[BBox]:
    merged: list[BBox] = []
    for box in sorted(boxes):
        for i, m in enumerate(merged):
            if _overlap(box, m) > 0 or _overlap(m, box) > 0:
                merged[i] = _union(m, box)
                break
        else:
            merged.append(box)
    return merged
