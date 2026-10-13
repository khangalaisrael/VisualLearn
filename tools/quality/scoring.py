"""Scores one slide analysis against what the slide plainly shows
(tools/quality/cases/cases.json). Pure functions, no model, so they are
unit-tested in tests/backend/test_quality_scoring.py.

Text is compared after `normalize`, which ignores spacing, case and the
usual ways the same maths can be written (LaTeX or Unicode, \\frac{n}{2} or
n/2, x_1 or x₁), so a case fails because something was misread or missed,
not because it was typeset differently. Code lines only ignore spacing.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_LATEX_SYMBOLS = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "varepsilon": "ε",
    "theta": "θ",
    "lambda": "λ",
    "mu": "μ",
    "pi": "π",
    "sigma": "σ",
    "phi": "φ",
    "omega": "ω",
    "Theta": "θ",
    "Omega": "ω",
    "Sigma": "σ",
    "Delta": "δ",
    "Lambda": "λ",
    "Phi": "φ",
    "oplus": "⊕",
    "otimes": "⊗",
    "cdot": "·",
    "times": "×",
    "le": "≤",
    "leq": "≤",
    "ge": "≥",
    "geq": "≥",
    "ne": "≠",
    "neq": "≠",
    "to": "→",
    "rightarrow": "→",
    "infty": "∞",
    "in": "∈",
    "sum": "∑",
}
_SPACING = re.compile(r"\\(?:left|right|big|Big|bigg|Bigg|quad|qquad|displaystyle|mathrm|text|operatorname)\b|\\[,;:! ]")
_FRAC = re.compile(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}")
_COMMAND = re.compile(r"\\([A-Za-z]+)")
_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉ₙ⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789n0123456789")
_DASHES = str.maketrans({"−": "-", "–": "-", "—": "-", "‐": "-"})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_SUBSCRIPTS).translate(_DASHES)
    text = _SPACING.sub("", text)
    text = _FRAC.sub(r"\1/\2", text)
    text = _COMMAND.sub(lambda m: _LATEX_SYMBOLS.get(m.group(1), m.group(1)), text)
    text = re.sub(r"[{}_^\s$]", "", text)
    return text.casefold()


def normalize_code(text: str) -> str:
    """Code only ignores spacing (indentation, alignment): an underscore or a case change is a misreading."""
    return re.sub(r"\s", "", unicodedata.normalize("NFC", text))


@dataclass
class CaseScore:
    image: str
    types_found: int = 0
    types_total: int = 0
    text_found: int = 0
    text_total: int = 0
    code_found: int = 0
    code_total: int = 0
    missing: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def score(self) -> float:
        """Share of all expectations met, 0..1; an analysis that failed scores 0."""
        if self.error:
            return 0.0
        total = self.types_total + self.text_total + self.code_total
        return (self.types_found + self.text_found + self.code_found) / total if total else 1.0


def _all_text(summary: str, objects: list) -> str:
    parts = [summary or ""]
    for obj in objects:
        parts.extend(value for value in (obj.extracted_text, obj.latex, obj.summary) if value)
        if obj.graph_structure is not None:
            parts.extend(obj.graph_structure.nodes)
    return "\n".join(parts)


def score_case(case: dict, summary: str, objects: list) -> CaseScore:
    """`objects` are the analyzer's SlideObjects for the case's image."""
    result = CaseScore(image=case["image"])

    found_types = {obj.type for obj in objects}
    for wanted in case.get("types", []):
        result.types_total += 1
        if found_types & set(wanted.split("|")):
            result.types_found += 1
        else:
            result.missing.append(f"type {wanted}")

    haystack = normalize(_all_text(summary, objects))
    for wanted in case.get("text", []):
        options = wanted if isinstance(wanted, list) else [wanted]
        result.text_total += 1
        if any(normalize(option) in haystack for option in options):
            result.text_found += 1
        else:
            result.missing.append(f"text {options[0]!r}")

    code = case.get("code")
    if code:
        language = code.get("language")
        blocks = [obj for obj in objects if obj.type == "code"]
        matching = [obj for obj in blocks if not language or (obj.language or "").lower() == language.lower()]
        if blocks and not matching:
            result.missing.append(f"code language {language} (read as {', '.join(sorted({str(b.language) for b in blocks}))})")
        code_text = normalize_code("\n".join(obj.extracted_text or "" for obj in matching))
        for line in code["lines"]:
            result.code_total += 1
            if normalize_code(line) in code_text:
                result.code_found += 1
            else:
                result.missing.append(f"code {line!r}")
    return result
