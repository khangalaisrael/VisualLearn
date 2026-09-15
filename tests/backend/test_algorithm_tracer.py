"""Tests for backend/app/services/algorithm_tracer.py — deterministic
execution tracing for the sorting/searching catalog (docs/AlgorithmsMVP.md
Phase 3). Pure function tests, no DB/app fixtures needed."""

import pytest

from app.services.algorithm_tracer import find_algorithm_name, find_array, find_target, trace

_UNSORTED = [5.0, 2.0, 4.0, 6.0, 1.0, 3.0]


@pytest.mark.parametrize(
    "algorithm_key",
    ["bubble_sort", "insertion_sort", "selection_sort", "merge_sort", "quick_sort", "heap_sort"],
)
def test_sorting_algorithms_match_pythons_sorted(algorithm_key):
    result = trace(algorithm_key, _UNSORTED, None)
    assert result is not None
    assert result.result == sorted(_UNSORTED)
    assert result.steps[0].startswith("start:")
    assert result.steps[-1].startswith("final:")


def test_sorting_trace_is_stable_across_runs():
    # A trace over the model's own reasoning wouldn't be — this one must
    # be, since it's produced by literally running the algorithm.
    first = trace("insertion_sort", _UNSORTED, None)
    second = trace("insertion_sort", _UNSORTED, None)
    assert first.steps == second.steps


def test_linear_search_finds_correct_index():
    result = trace("linear_search", _UNSORTED, 6.0)
    assert result is not None
    assert result.result == _UNSORTED.index(6.0)


def test_linear_search_reports_not_found():
    result = trace("linear_search", _UNSORTED, 999.0)
    assert result is not None
    assert result.result == -1
    assert "not found" in result.steps[-1]


def test_binary_search_on_sorted_input_finds_correct_index():
    sorted_arr = sorted(_UNSORTED)
    result = trace("binary_search", sorted_arr, 6.0)
    assert result is not None
    assert result.result == sorted_arr.index(6.0)


def test_binary_search_on_unsorted_input_refuses_rather_than_fakes_it():
    # docs/TheoryOfAlgorithm.md §23: "binary search works on any array" is
    # a named misconception — the checker must not silently validate it.
    result = trace("binary_search", _UNSORTED, 6.0)
    assert result is None


def test_search_without_target_returns_none():
    assert trace("linear_search", _UNSORTED, None) is None
    assert trace("binary_search", sorted(_UNSORTED), None) is None


def test_unrecognized_algorithm_returns_none():
    assert trace("bogosort", _UNSORTED, None) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Trace insertion sort on this array", "insertion_sort"),
        ("What does bubblesort do here?", "bubble_sort"),
        ("Can you run mergesort on [1,2,3]?", "merge_sort"),
        ("Explain this slide", None),
    ],
)
def test_find_algorithm_name(text, expected):
    assert find_algorithm_name(text) == expected


def test_find_array_extracts_numeric_literal():
    assert find_array("Trace this on [5, 2, 4, 6, 1, 3]") == [5.0, 2.0, 4.0, 6.0, 1.0, 3.0]


def test_find_array_returns_none_without_a_literal():
    assert find_array("Trace this on the array from the slide") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("search for 4 using binary search", 4.0),
        ("target = 7", 7.0),
        ("target: -3", -3.0),
        ("no target mentioned here", None),
    ],
)
def test_find_target(text, expected):
    assert find_target(text) == expected
