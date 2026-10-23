import json
from pathlib import Path
from types import SimpleNamespace

from audiobook.extract import extract
from audiobook.model import Mode, Script, SegmentKind
from audiobook.narrators.claude import ClaudeNarrator, SegmentOut, WindowOut
from audiobook.narrators.rules import RuleNarrator
from audiobook.render import render, split_chapters
from audiobook.voices.silent import SilentVoice

SAMPLE = Path(__file__).parent.parent / "samples" / "sample-paper.pdf"


def test_rule_narrator_read_mode():
    doc = extract(SAMPLE)
    script = RuleNarrator().narrate(doc, Mode.READ)
    spoken = " ".join(s.text for s in script.segments)
    assert "Section 2. Method." in spoken
    assert "L of theta equals" in spoken
    assert "Figure 1: Training loss" in spoken
    assert "[1]" not in spoken and "J. Doe" not in spoken  # citations and bibliography skipped
    assert "Code and data are available" not in spoken  # footnotes skipped in Read mode
    assert spoken.count("references is skipped") == 1


def test_script_round_trips_through_json():
    doc = extract(SAMPLE)
    script = RuleNarrator().narrate(doc, Mode.READ)
    assert Script.from_json(script.to_json()) == script


def test_render_writes_chapters_and_sync_map(tmp_path):
    doc = extract(SAMPLE)
    script = RuleNarrator().narrate(doc, Mode.READ)
    book = render(doc, script, SilentVoice(), tmp_path, audio_format="wav")

    assert [c["title"] for c in book["chapters"]][:3] == ["Tiny Models Learn Fast", "Abstract", "Section 1. Introduction"]
    for chapter in book["chapters"]:
        assert (tmp_path / chapter["file"]).exists()
    assert (tmp_path / Path(book["source_pdf"]).name).exists()  # the player opens the PDF next to book.json

    on_disk = json.loads((tmp_path / "book.json").read_text())
    segments = on_disk["segments"]
    starts = [s["start"] for s in segments]
    assert starts == sorted(starts)
    assert on_disk["duration"] >= segments[-1]["end"] - 0.01

    equation = next(s for s in segments if s["text"].startswith("L of theta"))
    assert equation["anchors"][0]["page"] == 0
    assert equation["sentences"][0]["start"] >= equation["start"]


def test_split_chapters_starts_at_headings():
    doc = extract(SAMPLE)
    chapters = split_chapters(RuleNarrator().narrate(doc, Mode.READ))
    assert all(c.segments[0][1].kind == SegmentKind.HEADING for c in chapters)


class FakeMessages:
    def __init__(self):
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        user_text = kwargs["messages"][0]["content"][-1]["text"]
        page = "p1" if '"page": 1' in user_text else "p2"
        out = WindowOut(
            segments=[
                SegmentOut(kind="read", text="Recent work [1] agrees.", source=[f"{page}-b1", "made-up-id"]),
                SegmentOut(kind="aside", text="This equation says the model should be confident and right.",
                           source=[f"{page}-b1"], style="warm"),
                SegmentOut(kind="pause", text=""),
            ],
            summary=f"summary after {page}",
        )
        return SimpleNamespace(stop_reason="end_turn", parsed_output=out, stop_details=None)


def test_claude_narrator_windows_and_validates_output():
    doc = extract(SAMPLE)
    messages = FakeMessages()
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    script = ClaudeNarrator(client=client, pages_per_call=1, log=open("/dev/null", "w")).narrate(doc, Mode.EXPLAIN)

    assert len(messages.calls) == 2  # one call per page
    first, second = messages.calls
    assert sum(1 for c in first["messages"][0]["content"] if c["type"] == "image") == 1
    assert "EXPLAIN" in first["system"][0]["text"]
    assert "summary after p1" in second["messages"][0]["content"][-1]["text"]  # running summary carried over

    read = script.segments[0]
    assert read.text == "Recent work agrees."  # speech-text safety net applied to read segments
    assert read.source == ["p1-b1"]  # unknown ids dropped
    assert script.segments[1].kind == SegmentKind.ASIDE and script.segments[1].style == "warm"
    assert script.mode == Mode.EXPLAIN
