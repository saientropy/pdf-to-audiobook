from pathlib import Path

import pytest

from audiobook.extract import _join_lines, extract
from audiobook.model import BlockKind

SAMPLE = Path(__file__).parent.parent / "samples" / "sample-paper.pdf"


@pytest.fixture(scope="module")
def doc():
    return extract(SAMPLE)


def texts(doc, kind):
    return [b.text for b in doc.blocks if b.kind == kind]


def test_title(doc):
    assert doc.title == "Tiny Models Learn Fast"


def test_running_header_and_page_numbers_are_dropped(doc):
    all_text = " ".join(b.text for b in doc.blocks)
    assert "Journal of Small Results" not in all_text
    assert not any(b.text.strip() in {"1", "2"} for b in doc.blocks)


def test_headings(doc):
    assert texts(doc, BlockKind.HEADING) == [
        "Tiny Models Learn Fast", "Abstract", "1 Introduction", "2 Method",
        "3 Results", "4 Conclusion", "References",
    ]


def test_hyphenated_line_break_is_joined(doc):
    intro = next(t for t in texts(doc, BlockKind.PARAGRAPH) if t.startswith("Large models"))
    assert "useful on devices" in intro


def test_equation_detected(doc):
    [eq] = texts(doc, BlockKind.EQUATION)
    assert eq.startswith("L(θ)")


def test_figure_gets_caption_and_absorbs_axis_labels(doc):
    [fig] = texts(doc, BlockKind.FIGURE)
    assert fig.startswith("Figure 1: Training loss")
    paragraphs = texts(doc, BlockKind.PARAGRAPH)
    assert "loss" not in paragraphs and "epoch" not in paragraphs


def test_sentence_mentioning_figure_is_not_a_caption(doc):
    assert any(t.startswith("Figure 1 shows the training loss") for t in texts(doc, BlockKind.PARAGRAPH))


def test_table_rows_and_caption(doc):
    [table] = texts(doc, BlockKind.TABLE)
    assert table.splitlines()[0] == "Table 1: Accuracy on the toy task."
    assert "Ours | 0.4M | 88.5%" in table


def test_code_footnote_and_references(doc):
    assert texts(doc, BlockKind.CODE)[0].startswith("for epoch in range(10):")
    assert texts(doc, BlockKind.FOOTNOTE)[0].startswith("¹ Code and data")
    assert texts(doc, BlockKind.REFERENCES)[0].startswith("[1] J. Doe")


def test_reading_order_follows_the_page(doc):
    kinds = [b.kind for b in doc.blocks if b.page == 1]
    assert kinds[:4] == [BlockKind.HEADING, BlockKind.PARAGRAPH, BlockKind.FIGURE, BlockKind.TABLE]


def test_join_lines_keeps_real_hyphens():
    assert _join_lines(["state-", "of-the-art"]) == "state-of-the-art"
    assert _join_lines(["learn-", "ing rate"]) == "learning rate"
