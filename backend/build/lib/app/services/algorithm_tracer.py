"""Deterministic (non-LLM) execution tracing for the sorting/searching
catalog (docs/AlgorithmsMVP.md Phase 3, docs/TheoryOfAlgorithm.md §12/§15/
§16). Runs real, instrumented reference implementations instead of asking
the chat model to simulate execution step-by-step in its head — same
"verify, don't trust the model's own work" pattern as recurrence_solver.py
for Master Theorem.

Deliberately narrow: a fixed catalog of well-known algorithms, matched by
keyword against the student's question and the slide's extracted text —
not by understanding arbitrary code the VLM extracted. If the algorithm
or the input array isn't recognized, no trace is produced — never one
based on a guess about which algorithm is meant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class TraceResult:
    algorithm: str
    input: list[float]
    steps: list[str]
    result: list[float] | int


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def _fmt(arr: list[float]) -> str:
    return "[" + ", ".join(_num(x) for x in arr) + "]"


def format_result(result: list[float] | int) -> str:
    """Formats a `TraceResult.result` the same way steps are formatted
    (integers displayed without a trailing `.0`) — for callers rendering
    it outside this module, e.g. chat.py's trace context block."""
    return _fmt(result) if isinstance(result, list) else _num(result)


def _trace_bubble_sort(arr: list[float]) -> TraceResult:
    a = list(arr)
    steps = [f"start: {_fmt(a)}"]
    n = len(a)
    for i in range(n):
        swapped = False
        for j in range(n - i - 1):
            steps.append(f"compare a[{j}]={_num(a[j])} and a[{j + 1}]={_num(a[j + 1])}")
            if a[j] > a[j + 1]:
                a[j], a[j + 1] = a[j + 1], a[j]
                swapped = True
                steps.append(f"swap -> {_fmt(a)}")
        if not swapped:
            steps.append("no swaps this pass, already sorted — stopping early")
            break
    steps.append(f"final: {_fmt(a)}")
    return TraceResult("bubble_sort", arr, steps, a)


def _trace_insertion_sort(arr: list[float]) -> TraceResult:
    a = list(arr)
    steps = [f"start: {_fmt(a)}"]
    for i in range(1, len(a)):
        key = a[i]
        j = i - 1
        steps.append(f"i={i}: key=a[{i}]={_num(key)}")
        while j >= 0 and a[j] > key:
            steps.append(f"a[{j}]={_num(a[j])} > key={_num(key)}, shift right")
            a[j + 1] = a[j]
            j -= 1
        a[j + 1] = key
        steps.append(f"insert key at index {j + 1} -> {_fmt(a)}")
    steps.append(f"final: {_fmt(a)}")
    return TraceResult("insertion_sort", arr, steps, a)


def _trace_selection_sort(arr: list[float]) -> TraceResult:
    a = list(arr)
    steps = [f"start: {_fmt(a)}"]
    n = len(a)
    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            steps.append(f"compare a[{j}]={_num(a[j])} to current min a[{min_idx}]={_num(a[min_idx])}")
            if a[j] < a[min_idx]:
                min_idx = j
        if min_idx != i:
            a[i], a[min_idx] = a[min_idx], a[i]
            steps.append(f"swap a[{i}] and a[{min_idx}] -> {_fmt(a)}")
        else:
            steps.append(f"a[{i}] is already the minimum of the remaining unsorted range")
    steps.append(f"final: {_fmt(a)}")
    return TraceResult("selection_sort", arr, steps, a)


def _trace_merge_sort(arr: list[float]) -> TraceResult:
    steps: list[str] = [f"start: {_fmt(arr)}"]

    def merge_sort(sub: list[float], depth: int) -> list[float]:
        indent = "  " * depth
        if len(sub) <= 1:
            steps.append(f"{indent}base case: {_fmt(sub)}")
            return sub
        mid = len(sub) // 2
        steps.append(f"{indent}divide {_fmt(sub)} -> {_fmt(sub[:mid])} and {_fmt(sub[mid:])}")
        left = merge_sort(sub[:mid], depth + 1)
        right = merge_sort(sub[mid:], depth + 1)
        merged: list[float] = []
        i = j = 0
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                j += 1
        merged.extend(left[i:])
        merged.extend(right[j:])
        steps.append(f"{indent}merge {_fmt(left)} and {_fmt(right)} -> {_fmt(merged)}")
        return merged

    result = merge_sort(list(arr), 0)
    steps.append(f"final: {_fmt(result)}")
    return TraceResult("merge_sort", arr, steps, result)


def _trace_quick_sort(arr: list[float]) -> TraceResult:
    steps: list[str] = [f"start: {_fmt(arr)}"]

    def quick_sort(sub: list[float], depth: int) -> list[float]:
        if len(sub) <= 1:
            return sub
        indent = "  " * depth
        pivot = sub[-1]
        steps.append(f"{indent}pivot = {_num(pivot)} in {_fmt(sub)}")
        less = [x for x in sub[:-1] if x <= pivot]
        greater = [x for x in sub[:-1] if x > pivot]
        steps.append(f"{indent}partition -> less={_fmt(less)}, pivot={_num(pivot)}, greater={_fmt(greater)}")
        return quick_sort(less, depth + 1) + [pivot] + quick_sort(greater, depth + 1)

    result = quick_sort(list(arr), 0)
    steps.append(f"final: {_fmt(result)}")
    return TraceResult("quick_sort", arr, steps, result)


def _trace_heap_sort(arr: list[float]) -> TraceResult:
    a = list(arr)
    steps = [f"start: {_fmt(a)}"]
    n = len(a)

    def heapify(size: int, root: int) -> None:
        largest = root
        left, right = 2 * root + 1, 2 * root + 2
        if left < size and a[left] > a[largest]:
            largest = left
        if right < size and a[right] > a[largest]:
            largest = right
        if largest != root:
            a[root], a[largest] = a[largest], a[root]
            steps.append(f"sift down: swap a[{root}] and a[{largest}] -> {_fmt(a)}")
            heapify(size, largest)

    for i in range(n // 2 - 1, -1, -1):
        heapify(n, i)
    steps.append(f"build max-heap -> {_fmt(a)}")
    for end in range(n - 1, 0, -1):
        a[0], a[end] = a[end], a[0]
        steps.append(f"move max to index {end}: swap a[0] and a[{end}] -> {_fmt(a)}")
        heapify(end, 0)
    steps.append(f"final: {_fmt(a)}")
    return TraceResult("heap_sort", arr, steps, a)


def _trace_linear_search(arr: list[float], target: float) -> TraceResult:
    steps = [f"start: {_fmt(arr)}, target={_num(target)}"]
    for i, x in enumerate(arr):
        steps.append(f"check a[{i}]={_num(x)}")
        if x == target:
            steps.append(f"found target at index {i}")
            return TraceResult("linear_search", arr, steps, i)
    steps.append("target not found")
    return TraceResult("linear_search", arr, steps, -1)


def _trace_binary_search(arr: list[float], target: float) -> TraceResult | None:
    if arr != sorted(arr):
        # Binary search's precondition (sorted input) doesn't hold —
        # producing a trace would misrepresent the algorithm as correct
        # on data it isn't valid for. See docs/TheoryOfAlgorithm.md §23's
        # "binary search works on any array" misconception.
        return None
    steps = [f"start: {_fmt(arr)}, target={_num(target)} (array is sorted, precondition holds)"]
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        steps.append(f"lo={lo}, hi={hi}, mid={mid}, a[mid]={_num(arr[mid])}")
        if arr[mid] == target:
            steps.append(f"found target at index {mid}")
            return TraceResult("binary_search", arr, steps, mid)
        if arr[mid] < target:
            steps.append("a[mid] < target, search the right half")
            lo = mid + 1
        else:
            steps.append("a[mid] > target, search the left half")
            hi = mid - 1
    steps.append("target not found")
    return TraceResult("binary_search", arr, steps, -1)


_SORT_CATALOG: dict[str, tuple[list[str], "callable"]] = {
    "bubble_sort": (["bubble sort", "bubblesort"], _trace_bubble_sort),
    "insertion_sort": (["insertion sort"], _trace_insertion_sort),
    "selection_sort": (["selection sort"], _trace_selection_sort),
    "merge_sort": (["merge sort", "mergesort"], _trace_merge_sort),
    "quick_sort": (["quick sort", "quicksort"], _trace_quick_sort),
    "heap_sort": (["heap sort", "heapsort"], _trace_heap_sort),
}
_SEARCH_CATALOG: dict[str, tuple[list[str], "callable"]] = {
    "linear_search": (["linear search"], _trace_linear_search),
    "binary_search": (["binary search"], _trace_binary_search),
}
_CATALOG = {**_SORT_CATALOG, **_SEARCH_CATALOG}

_ARRAY_PATTERN = re.compile(r"\[\s*-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)*\s*\]")
_TARGET_PATTERN = re.compile(
    r"target\s*(?:is|=|:)?\s*(-?\d+(?:\.\d+)?)|search(?:ing)?\s+for\s+(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def find_algorithm_name(text: str) -> str | None:
    """Returns the catalog key of the first recognized algorithm name
    mentioned in `text` (case-insensitive substring match), or None."""
    lowered = text.lower()
    for key, (phrases, _fn) in _CATALOG.items():
        if any(phrase in lowered for phrase in phrases):
            return key
    return None


def find_array(text: str) -> list[float] | None:
    """Returns the first `[1, 2, 3]`-style numeric array literal found in
    `text`, or None if there isn't one."""
    match = _ARRAY_PATTERN.search(text)
    if not match:
        return None
    numbers = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", match.group(0))]
    return numbers or None


def find_target(text: str) -> float | None:
    """Returns a search target mentioned in `text` (e.g. "target = 7",
    "searching for 7"), or None."""
    match = _TARGET_PATTERN.search(text)
    if not match:
        return None
    value = match.group(1) or match.group(2)
    return float(value)


def trace(algorithm_key: str, array: list[float], target: float | None) -> TraceResult | None:
    """Runs the named catalog algorithm on `array` (and `target`, for the
    two search algorithms) and returns its exact execution trace. Returns
    None for an unrecognized `algorithm_key`, a search algorithm with no
    `target`, or binary search on unsorted input — never a guessed trace."""
    if algorithm_key not in _CATALOG:
        return None
    _phrases, fn = _CATALOG[algorithm_key]
    if algorithm_key in _SEARCH_CATALOG:
        if target is None:
            return None
        return fn(array, target)
    return fn(array)
