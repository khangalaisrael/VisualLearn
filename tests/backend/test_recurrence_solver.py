"""Tests for backend/app/services/recurrence_solver.py — deterministic
Master Theorem verification (docs/AlgorithmsMVP.md Phase 2). Pure
function tests, no DB/app fixtures needed."""

import pytest

from app.services.recurrence_solver import analyze_recurrence


@pytest.mark.parametrize(
    ("expression", "expected_case", "expected_complexity"),
    [
        ("T(n) = 2T(n/2) + n", "case_2", "Θ(n log n)"),  # merge sort
        ("T(n) = T(n/2) + 1", "case_2", "Θ(log n)"),  # binary search
        ("T(n) = 4T(n/2) + n", "case_1", "Θ(n^2)"),
        ("T(n) = T(n/2) + n^2", "case_3", "Θ(n^2)"),
        ("T(n) = 8T(n/2) + n^2", "case_1", "Θ(n^3)"),
        ("T(n) = 3T(n/2) + n", "case_1", "Θ(n^1.585)"),  # Karatsuba
        ("T(n) = 7T(n/2) + n^2", "case_1", "Θ(n^2.807)"),  # Strassen
        ("T(n) = 2T(n/2) + n*log(n)", "case_2", "Θ(n log^2 n)"),
    ],
)
def test_known_recurrences_match_textbook_results(expression, expected_case, expected_complexity):
    result = analyze_recurrence(expression)
    assert result is not None
    assert result.master_case == expected_case
    assert result.complexity == expected_complexity


def test_latex_form_from_vlm_extraction_parses_identically():
    # This is literally what the real VLM's `latex` field returns for
    # "T(n) = 2T(n/2) + n" (see the AlgorithmsMVP.md end-to-end verification).
    latex = r"T(n) = 2T\left(\frac{n}{2}\right) + n"
    result = analyze_recurrence(latex)
    assert result is not None
    assert result.a == 2.0
    assert result.b == 2.0
    assert result.complexity == "Θ(n log n)"


def test_unrecognized_f_n_shape_is_inconclusive_not_guessed():
    result = analyze_recurrence("T(n) = 2T(n/2) + 2^n")
    assert result is not None
    assert result.master_case == "inconclusive"
    assert result.complexity is None
    assert "isn't in a form this checker recognizes" in result.notes


@pytest.mark.parametrize(
    "expression",
    [
        "T(n) = T(n-1) + 1",  # linear recurrence, not divide-and-conquer form
        "not a recurrence at all",
        "T(n) = 2T(n/2) + 3T(n/3) + n",  # multiple recursive terms
    ],
)
def test_non_master_theorem_shapes_return_none(expression):
    assert analyze_recurrence(expression) is None


def test_recursion_tree_reflects_branching_factor_and_divisor():
    result = analyze_recurrence("T(n) = 3T(n/2) + n")
    assert result is not None
    assert "T(n)" in result.recursion_tree
    assert "T(n/2)" in result.recursion_tree
    assert "3^k" in result.recursion_tree
