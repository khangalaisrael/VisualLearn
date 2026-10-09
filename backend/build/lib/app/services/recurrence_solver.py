"""Deterministic (non-LLM) analysis of Master-Theorem-shaped recurrences.

Closes the verification gap flagged in docs/AlgorithmsMVP.md Phase 1: the
chat model's own complexity derivations weren't checked against anything.
For a recurrence of the standard form `T(n) = a*T(n/b) + f(n)`, this module
extracts `a`/`b`/`f(n)` with a regex — not by asking the model — and
computes the Master Theorem result exactly with sympy, independent of
whatever the chat model says. Same "don't trust the model, cross-check with
something deterministic" pattern as graph_topology.py's CV edge detection
for GraphStructure.

Deliberately narrow: only single-recursive-term recurrences with numeric
`a`/`b`, and `f(n)` expressible as `n^p * log(n)^k` for a small set of
recognized shapes. Anything else (multiple recursive terms, non-numeric
a/b, exponential f(n), etc.) returns `None` rather than guessing — same
"don't fabricate" discipline as the rest of the algorithms prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sympy

_RECURRENCE_PATTERN = re.compile(
    r"^T\(n\)=(?P<a>\d+(?:\.\d+)?)?\*?T\(n/(?P<b>\d+(?:\.\d+)?)\)\+(?P<f>.+)$"
)

# f(n) shapes this checker recognizes, each mapped to (polynomial_degree,
# log_power). Anything outside this small set returns None from
# `_classify_f_n` rather than being guessed at.
_F_N_SHAPES: list[tuple[re.Pattern[str], tuple[float, int] | None]] = [
    (re.compile(r"^1$"), (0.0, 0)),
    (re.compile(r"^log\(n\)$"), (0.0, 1)),
    (re.compile(r"^sqrt\(n\)$"), (0.5, 0)),
    (re.compile(r"^n$"), (1.0, 0)),
    (re.compile(r"^n\*log\(n\)$"), (1.0, 1)),
]


def _normalize(expr: str) -> str:
    """Strips whitespace and common LaTeX artifacts the VLM's `latex` field
    may contain (docs/analysis.v4 prompt), so `T(n) = 2T\\left(\\frac{n}{2}
    \\right) + n` and `T(n)=2T(n/2)+n` both reach the same regex."""
    expr = expr.strip()
    expr = expr.replace("\\left", "").replace("\\right", "")
    expr = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"\1/\2", expr)
    expr = expr.replace("\\cdot", "*").replace("\\times", "*").replace("\\,", "")
    expr = re.sub(r"\\log(?:_\{?\d+\}?)?", "log", expr)
    expr = expr.replace("\\sqrt", "sqrt").replace("$", "")
    expr = re.sub(r"\s+", "", expr)
    # "n^2" style carets survive; "n^{2}" braces don't matter to sympy but
    # the shape regexes above expect no braces, so strip them.
    expr = expr.replace("{", "").replace("}", "")
    # Bare space-separated "nlog(n)" from "n log n" after whitespace
    # stripping needs its implicit multiplication restored.
    expr = re.sub(r"(?<=n)log\(", "*log(", expr)
    return expr


def _classify_f_n(f_n: str) -> tuple[float, int] | None:
    for pattern, shape in _F_N_SHAPES:
        if pattern.match(f_n):
            return shape
    # n^p, with or without a following *log(n) factor.
    m = re.match(r"^n\^(?P<p>-?\d+(?:\.\d+)?)(?:\*log\(n\))?$", f_n)
    if m:
        return (float(m.group("p")), 1 if f_n.endswith("*log(n)") else 0)
    return None


def _format_exponent(log_b_a: sympy.Expr) -> str:
    simplified = sympy.nsimplify(log_b_a, rational=True, tolerance=1e-9)
    if simplified.is_Integer or (simplified.is_Rational and simplified.q <= 12):
        return str(simplified)
    return f"{float(log_b_a):.3f}"


def _ascii_tree(a: float, b: float, depth: int = 3) -> str:
    a_display = int(a) if a == int(a) else a
    b_display = int(b) if b == int(b) else b
    branch_count = min(int(a), 3) if a == int(a) else 2
    lines = ["T(n)"]
    indent = 0
    for level in range(1, depth + 1):
        indent += 2
        node_label = f"n/{b_display}^{level}" if level > 1 else f"n/{b_display}"
        branches = "   ".join([f"T({node_label})"] * branch_count)
        suffix = " ..." if a_display > branch_count else ""
        lines.append(" " * indent + branches + suffix)
    lines.append(f"... continues for log_{b_display}(n) levels, {a_display}^k subproblems at level k")
    return "\n".join(lines)


@dataclass
class RecurrenceAnalysis:
    a: float
    b: float
    f_n: str
    n_pow_log_b_a: str
    master_case: str  # "case_1" | "case_2" | "case_3" | "inconclusive"
    complexity: str | None
    recursion_tree: str
    notes: str


def analyze_recurrence(expression: str) -> RecurrenceAnalysis | None:
    """Returns a verified Master Theorem analysis for `expression`, or
    `None` if it doesn't match the recognized `T(n) = a*T(n/b) + f(n)`
    shape (with `a`, `b` numeric) — never a guess."""
    normalized = _normalize(expression)
    match = _RECURRENCE_PATTERN.match(normalized)
    if not match:
        return None

    a = float(match.group("a")) if match.group("a") else 1.0
    b = float(match.group("b"))
    f_n_raw = match.group("f")
    if a <= 0 or b <= 1:
        return None
    if "T(" in f_n_raw:
        # A second recursive term (e.g. "2T(n/2) + 3T(n/3) + n") isn't the
        # single-recursive-term shape Master Theorem covers — reject
        # outright rather than misreporting a/b from only the first term.
        return None

    log_b_a = sympy.log(sympy.nsimplify(a), sympy.nsimplify(b))
    log_b_a_value = float(log_b_a)
    log_b_a_display = _format_exponent(log_b_a)
    if log_b_a_display == "0":
        n_pow_display = "1"
    elif log_b_a_display == "1":
        n_pow_display = "n"
    else:
        n_pow_display = f"n^{log_b_a_display}"
    recursion_tree = _ascii_tree(a, b)

    shape = _classify_f_n(f_n_raw)
    if shape is None:
        return RecurrenceAnalysis(
            a=a,
            b=b,
            f_n=f_n_raw,
            n_pow_log_b_a=n_pow_display,
            master_case="inconclusive",
            complexity=None,
            recursion_tree=recursion_tree,
            notes=(
                f"f(n) = {f_n_raw} isn't in a form this checker recognizes "
                "(n^p, n^p·log(n), log(n), sqrt(n), or a constant) — Master "
                "Theorem comparison skipped rather than guessed. Derive this "
                "one by substitution or a recursion-tree argument instead."
            ),
        )

    p, k = shape
    eps = 1e-9
    if p < log_b_a_value - eps:
        complexity = f"Θ({n_pow_display})"
        notes = (
            f"f(n) = {f_n_raw} grows polynomially slower than {n_pow_display} "
            "(Master Theorem case 1) — the work done by the recursive calls "
            "dominates over the work done outside them."
        )
        case = "case_1"
    elif abs(p - log_b_a_value) <= eps:
        new_k = k + 1
        log_factor = "log n" if new_k == 1 else f"log^{new_k} n"
        complexity = f"Θ({log_factor})" if n_pow_display == "1" else f"Θ({n_pow_display} {log_factor})"
        notes = (
            f"f(n) = {f_n_raw} matches {n_pow_display}"
            + (f"·log^{k} n" if k else "")
            + " (Master Theorem case 2) — the work is balanced across all "
            "levels of the recursion, adding one extra log factor."
        )
        case = "case_2"
    else:
        complexity = f"Θ({f_n_raw})"
        notes = (
            f"f(n) = {f_n_raw} grows polynomially faster than {n_pow_display} "
            "(Master Theorem case 3) — the work done outside the recursive "
            "calls dominates, assuming the regularity condition "
            "a·f(n/b) ≤ c·f(n) holds (not separately checked here)."
        )
        case = "case_3"

    return RecurrenceAnalysis(
        a=a,
        b=b,
        f_n=f_n_raw,
        n_pow_log_b_a=n_pow_display,
        master_case=case,
        complexity=complexity,
        recursion_tree=recursion_tree,
        notes=notes,
    )
