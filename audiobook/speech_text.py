"""Rules that make written text sayable: drop citation markers, expand abbreviations, voice maths.

The LLM narrator does this itself; these rules power the offline narrator and also run as a safety
net over every segment before it reaches a voice engine.
"""

from __future__ import annotations

import re

_BRACKET_CITATION = re.compile(r"\s?\[\s*\d+(?:\s*[,–-]\s*\d+)*\s*\]")
_PAREN_CITATION = re.compile(
    r"\s?\((?:see\s+)?[A-Z][A-Za-z'’-]+(?:\s+(?:et\s+al\.?|and|&)\s*(?:[A-Z][A-Za-z'’-]+)?)?,?\s+\d{4}[a-z]?"
    r"(?:;\s*[A-Z][A-Za-z'’-]+(?:\s+(?:et\s+al\.?|and|&)\s*(?:[A-Z][A-Za-z'’-]+)?)?,?\s+\d{4}[a-z]?)*\)"
)
_FOOTNOTE_MARK = re.compile(r"(?<=[\w.,;:)\]])[¹²³⁴⁵⁶⁷⁸⁹⁰†‡]+")

ABBREVIATIONS = {
    r"\be\.g\.": "for example",
    r"\bi\.e\.": "that is",
    r"\betc\.": "et cetera",
    r"\bet al\.": "and colleagues",
    r"\bvs\.": "versus",
    r"\bFig\.\s?(?=\d)": "Figure ",
    r"\bFigs\.\s?(?=\d)": "Figures ",
    r"\bEq\.\s?(?=\(?\d)": "Equation ",
    r"\bEqs\.\s?(?=\(?\d)": "Equations ",
    r"\bSec\.\s?(?=\d)": "Section ",
    r"\bTab\.\s?(?=\d)": "Table ",
    r"\bapprox\.": "approximately",
    r"\bcf\.": "compare",
}

SYMBOLS = {
    "=": " equals ", "≈": " is approximately ", "≠": " is not equal to ", "≤": " is at most ",
    "≥": " is at least ", "<": " is less than ", ">": " is greater than ", "+": " plus ",
    "−": " minus ", "×": " times ", "·": " times ", "÷": " divided by ", "±": " plus or minus ",
    "∑": " the sum of ", "Σ": " the sum of ", "∏": " the product of ", "∫": " the integral of ",
    "√": " the square root of ", "∞": " infinity ", "∂": " partial ", "∇": " the gradient of ",
    "∈": " in ", "→": " goes to ", "∀": " for all ", "∃": " there exists ",
    "α": " alpha ", "β": " beta ", "γ": " gamma ", "δ": " delta ", "ε": " epsilon ", "θ": " theta ",
    "λ": " lambda ", "μ": " mu ", "π": " pi ", "σ": " sigma ", "τ": " tau ", "φ": " phi ",
    "ψ": " psi ", "ω": " omega ", "Δ": " delta ", "Ω": " omega ",
}
GREEK = "αβγδεθλμπστφψωΔΩ"
MAGNITUDES = {"K": "thousand", "M": "million", "B": "billion"}
SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉ᵢⱼₖₙₘₜ", "0123456789ijknmt")
SUPERSCRIPTS = {"²": " squared", "³": " cubed", "ⁿ": " to the n", "⁻¹": " inverse"}


def clean_prose(text: str) -> str:
    """Prepare a paragraph of the document's own words for speech."""
    text = _BRACKET_CITATION.sub("", text)
    text = _PAREN_CITATION.sub("", text)
    text = _FOOTNOTE_MARK.sub("", text)
    for pattern, spoken in ABBREVIATIONS.items():
        text = re.sub(pattern, spoken, text)
    text = re.sub(r"(\w)ᵢ", r"\1 sub i", text)
    text = text.replace("ŷ", "y hat").replace("x̂", "x hat")
    text = re.sub(r"\b([a-zA-Z])_([a-zA-Z0-9])\b", r"\1 sub \2", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s?([KMB])\b", lambda m: f"{m.group(1)} {MAGNITUDES[m.group(2)]}", text)
    text = re.sub(r"(?<![A-Za-z])[" + GREEK + r"](?![A-Za-z])", lambda m: SYMBOLS[m.group(0)].strip(), text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def speak_math(expr: str) -> str:
    """Best-effort spoken form of a formula, e.g. 'L(θ) = − (1/N) Σᵢ yᵢ log ŷᵢ (1)'."""
    expr = re.sub(r"\s*\(\d{1,3}[a-z]?\)\s*$", "", expr)  # equation number
    for sup, spoken in SUPERSCRIPTS.items():
        expr = expr.replace(sup, spoken)
    expr = re.sub(r"[ΣΣ∑]([ᵢⱼₖₙₘₜ])", lambda m: f" the sum over {m.group(1).translate(SUBSCRIPTS)} of ", expr)
    expr = expr.replace("ŷ", "y-hat").replace("x̂", "x-hat")
    expr = re.sub(r"([A-Za-z])\(([^()]{1,12})\)", r"\1 of \2", expr)
    expr = re.sub(r"\(1/([A-Za-z0-9]+)\)", r"one over \1", expr)
    expr = re.sub(r"([A-Za-z0-9]+)\s*/\s*([A-Za-z0-9]+)", r"\1 over \2", expr)
    expr = re.sub(r"([\w-])([₀₁₂₃₄₅₆₇₈₉ᵢⱼₖₙₘₜ]+)", lambda m: f"{m.group(1)} sub {m.group(2).translate(SUBSCRIPTS)}", expr)
    expr = re.sub(r"([A-Za-z0-9])_\{?([A-Za-z0-9]+)\}?", r"\1 sub \2", expr)
    expr = re.sub(r"([A-Za-z0-9])\^\{?([A-Za-z0-9]+)\}?", r"\1 to the power \2", expr)
    for sym, spoken in SYMBOLS.items():
        expr = expr.replace(sym, spoken)
    expr = expr.replace("-hat", " hat").replace("(", " ").replace(")", " ")
    return re.sub(r"\s{2,}", " ", expr).strip()


def split_sentences(text: str) -> list[str]:
    """Split into sentences for finer-grained sync. Keeps abbreviations like 'e.g.' intact."""
    protected = re.sub(r"\b(Mr|Mrs|Ms|Dr|Prof|St|vs|al|Fig|Eq|No)\.", r"\1<dot>", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[\"'“(A-Z0-9])", protected)
    return [p.replace("<dot>", ".").strip() for p in parts if p.strip()]
