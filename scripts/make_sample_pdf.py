"""Generate a small, paper-like sample PDF that exercises every content type the narrator handles.

It has running headers, page-number footers, citation markers, a hyphenated line break, a display
equation, a vector figure with a caption, a table, a code listing, a footnote and a bibliography.

    python scripts/make_sample_pdf.py samples/sample-paper.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

W, H = 612, 792
MARGIN = 72
HEADER = "Journal of Small Results · Vol. 3 (2026)"

# Base-14 PDF fonts cannot draw θ, Σ or ŷ, so the maths uses DejaVu when it is installed.
_DEJAVU = Path("/usr/share/fonts/truetype/dejavu")
FONTFILES = {
    "dvs": _DEJAVU / "DejaVuSerif.ttf",
    "dvi": _DEJAVU / "DejaVuSerif.ttf",  # upright: DejaVu Serif Italic is not always installed
}


def font_args(font: str) -> dict:
    path = FONTFILES.get(font)
    if path is None:
        return {"fontname": font}
    if path.exists():
        return {"fontname": font, "fontfile": str(path)}
    return {"fontname": "tiit" if font == "dvi" else "tiro"}


class Writer:
    def __init__(self) -> None:
        self.doc = pymupdf.open()
        self.page: pymupdf.Page | None = None
        self.y = 0.0
        self.new_page()

    def new_page(self) -> None:
        self.page = self.doc.new_page(width=W, height=H)
        n = self.doc.page_count
        self.page.insert_text((MARGIN, 40), HEADER, fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
        self.page.insert_text((W / 2 - 4, H - 36), str(n), fontsize=9, fontname="helv")
        self.y = MARGIN

    def ensure(self, height: float) -> None:
        if self.y + height > H - 90:
            self.new_page()

    def text(self, s: str, size: float = 10.5, font: str = "tiro", gap: float = 8, align: int = 0,
             height: float | None = None) -> None:
        lines = s.count("\n") + 1
        h = height or max(size * 1.45 * (len(s) / 85 + lines), size * 2)
        self.ensure(h)
        rect = pymupdf.Rect(MARGIN, self.y, W - MARGIN, self.y + h)
        left = self.page.insert_textbox(rect, s, fontsize=size, align=align, **font_args(font))
        used = h - left if left >= 0 else h
        self.y += used + gap

    def figure(self) -> None:
        self.ensure(200)
        x0, y0, x1, y1 = 180, self.y + 10, 430, self.y + 160
        p = self.page
        p.draw_line((x0, y1), (x1, y1))
        p.draw_line((x0, y1), (x0, y0))
        pts = [(x0 + i * 25, y0 + 10 + 120 * (1 - 0.7 ** i)) for i in range(11)]  # falls, then flattens
        p.draw_polyline(pts, color=(0.1, 0.3, 0.8), width=1.5)
        p.insert_text((x0 + 90, y1 + 14), "epoch", fontsize=8, fontname="helv")
        p.insert_text((x0 - 26, y0 + 70), "loss", fontsize=8, fontname="helv")
        self.y = y1 + 24
        self.text("Figure 1: Training loss of the tiny model. Loss falls quickly in the first five epochs "
                  "and then flattens out.", size=9, font="helv", align=1)

    def table(self, rows: list[list[str]]) -> None:
        self.ensure(20 * len(rows) + 20)
        col_w = (W - 2 * MARGIN) / len(rows[0])
        top = self.y
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                x0, y0 = MARGIN + c * col_w, top + r * 18
                self.page.draw_rect(pymupdf.Rect(x0, y0, x0 + col_w, y0 + 18), width=0.5)
                self.page.insert_text((x0 + 4, y0 + 13), cell, fontsize=9,
                                      fontname="hebo" if r == 0 else "helv")
        self.y = top + 18 * len(rows) + 10

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(path)


def build(path: Path) -> None:
    w = Writer()
    w.text("Tiny Models Learn Fast", size=20, font="tibo", align=1, gap=4)
    w.text("A. Researcher and B. Scientist", size=11, align=1, gap=14)
    w.text("Abstract", size=12, font="tibo", gap=2)
    w.text("We show that a very small neural network can learn a toy task in a handful of epochs. "
           "We describe the model, the loss we minimise, and a comparison against two baselines.")
    w.text("1  Introduction", size=13, font="tibo", gap=4)
    w.text("Large models dominate recent work [1, 2], but small models remain useful on de-\n"
           "vices with little memory (Smith et al., 2020). Prior studies of compact networks [3] focus on "
           "image tasks; we study a simple sequence task instead.¹")
    w.text("2  Method", size=13, font="tibo", gap=4)
    w.text("Given inputs xᵢ with labels yᵢ, the model predicts ŷᵢ and is trained to minimise the "
           "cross-entropy loss:", font="dvs")
    w.text("L(θ) = − (1/N) Σᵢ yᵢ log ŷᵢ        (1)", size=11, font="dvi", align=1)
    w.text("Here θ are the model parameters and N is the number of training examples. Equation (1) "
           "is minimised with stochastic gradient descent.", font="dvs")
    w.page.insert_text((MARGIN, H - 70), "¹ Code and data are available from the authors on request.",
                       fontsize=7.5, fontname="tiro")
    w.new_page()
    w.text("3  Results", size=13, font="tibo", gap=4)
    w.text("Figure 1 shows the training loss. Table 1 compares our model against two baselines.")
    w.figure()
    w.text("Table 1: Accuracy on the toy task.", size=9, font="helv", align=1, gap=4)
    w.table([["Model", "Params", "Accuracy"], ["Baseline A", "5M", "81.2%"],
             ["Baseline B", "12M", "84.0%"], ["Ours", "0.4M", "88.5%"]])
    w.text("The training loop is short:")
    w.text("for epoch in range(10):\n    for x, y in loader:\n        loss = criterion(model(x), y)\n"
           "        loss.backward()\n        optimizer.step()", size=9, font="cour", height=70)
    w.text("4  Conclusion", size=13, font="tibo", gap=4)
    w.text("A model with 0.4M parameters beats baselines thirty times its size on this task. Future work "
           "will test whether this holds on real data.")
    w.text("References", size=13, font="tibo", gap=4)
    w.text("[1] J. Doe. Scaling laws for everything. In Proc. of Big Conf, pages 1-10, 2023.\n"
           "[2] K. Lee and M. Park. Bigger is better. arXiv:2401.00001, 2024.\n"
           "[3] L. Smith, R. Jones, and T. Wu. Compact nets. J. Small Models, 4(2):11-19, 2020.",
           size=9, height=60)
    w.save(path)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/sample-paper.pdf")
    build(out)
    print(out)
