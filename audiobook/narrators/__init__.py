"""Step 2: narrators turn an extracted Document into a Script of things to say.

- RuleNarrator: offline, deterministic, Read mode only. Good for plain prose and for tests.
- ClaudeNarrator: looks at each page (image + extracted blocks) and writes what a good narrator or
  tutor would say, including explanations of formulas, figures, tables and code.
"""

from __future__ import annotations

from typing import Protocol

from ..model import Document, Mode, Script


class Narrator(Protocol):
    def narrate(self, doc: Document, mode: Mode) -> Script: ...


def get_narrator(name: str, **kwargs) -> Narrator:
    if name == "rules":
        from .rules import RuleNarrator

        return RuleNarrator()
    if name == "claude":
        from .claude import ClaudeNarrator

        return ClaudeNarrator(**kwargs)
    raise ValueError(f"unknown narrator {name!r} (expected 'rules' or 'claude')")
