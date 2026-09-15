"""Manual eval harness for the Theory of Algorithms chat pipeline
(docs/AlgorithmsMVP.md). This was flagged as a Phase 1 deliverable
("a short eval set... to catch regressions before shipping") but never
actually built until now, five phases in.

This hits the REAL chat model over HTTP (not FakeChatService) — it costs
real API money and its softer checks are not fully deterministic, so it
is NOT part of `pytest`/CI. Run it by hand after prompt changes:

    cd backend && python ../tools/eval_algorithms.py

Requires:
- The Docker stack running (`docker compose up -d db redis backend`,
  backend on host port 8001 per docker-compose.yml) with a real
  OPENAI_API_KEY/ANTHROPIC_API_KEY configured.
- Run from a shell where `app.*` imports resolve (the backend venv —
  see backend/README.md), since this seeds slide/object rows directly
  via the repositories (SQLAlchemy against the real Postgres instance,
  same DATABASE_URL the backend container uses via .env) rather than
  going through /slides/analyze — isolating "is the chat prompt good"
  from "did the VLM extract this slide correctly", which is already a
  separate, already-observed source of variance (see AlgorithmsMVP.md
  Phase 4's missing-edge-weight live test).

Each case's checks are intentionally simple substring/heuristic checks,
not full LLM-graded quality scoring — good enough to catch the kind of
regression this project has actually hit (e.g. Phase 5's socratic mode
silently giving the full answer away), not a rigorous quality bar.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Θ/Ω/etc. in check output crash cp1252 consoles otherwise

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.schemas import BoundingBox, GraphEdge, GraphStructure, SlideObject  # noqa: E402
from app.repositories.objects import ObjectRepository  # noqa: E402
from app.repositories.presentations import PresentationRepository  # noqa: E402
from app.repositories.slides import SlideRepository  # noqa: E402

BASE_URL = os.environ.get("EVAL_BASE_URL", "http://localhost:8001")
API_KEY = os.environ.get("LOCAL_API_KEY") or get_settings().local_api_key

Check = Callable[[str], tuple[bool, str]]


def _normalize(text: str) -> str:
    """The chat model formats math as LaTeX per the algorithm prompt (e.g.
    `\\Theta(n \\log n)`, `index \\(4\\)`), not the literal Unicode/plain
    text a naive substring check would expect — strip LaTeX punctuation
    so checks match the answer regardless of exactly how it was
    delimited/escaped."""
    text = text.lower()
    text = re.sub(r"[\\${}()[\]]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains(*needles: str) -> Check:
    def check(text: str) -> tuple[bool, str]:
        normalized = _normalize(text)
        missing = [n for n in needles if _normalize(n) not in normalized]
        if missing:
            return False, f"missing: {missing}"
        return True, "ok"

    return check


def any_of(*needles: str) -> Check:
    """Passes if at least one needle is present — for cases where the
    model could reasonably phrase the same idea several ways (e.g.
    "nested loops" vs. "inner loop"/"outer loop")."""

    def check(text: str) -> tuple[bool, str]:
        normalized = _normalize(text)
        if any(_normalize(n) in normalized for n in needles):
            return True, "ok"
        return False, f"none present: {list(needles)}"

    return check


def not_contains(*needles: str) -> Check:
    def check(text: str) -> tuple[bool, str]:
        normalized = _normalize(text)
        present = [n for n in needles if _normalize(n) in normalized]
        if present:
            return False, f"should not contain: {present}"
        return True, "ok"

    return check


def ends_with_question() -> Check:
    def check(text: str) -> tuple[bool, str]:
        stripped = text.strip()
        ok = stripped.endswith("?")
        return ok, "ok" if ok else "response doesn't end with a question mark"

    return check


def word_count_between(low: int, high: int) -> Check:
    def check(text: str) -> tuple[bool, str]:
        n = len(text.split())
        ok = low <= n <= high
        return ok, "ok" if ok else f"word count {n} outside [{low}, {high}]"

    return check


@dataclass
class SlideSeed:
    """Objects to insert directly (bypassing /slides/analyze and the VLM
    — see module docstring for why)."""

    objects: list[SlideObject] = field(default_factory=list)


@dataclass
class EvalCase:
    name: str
    message: str
    explanation_mode: str = "university"
    seed: SlideSeed = field(default_factory=SlideSeed)
    checks: list[Check] = field(default_factory=list)


CASES: list[EvalCase] = [
    EvalCase(
        name="phase1_loop_complexity_no_verified_block",
        message="What is the time complexity of this loop?",
        seed=SlideSeed(
            [
                SlideObject(
                    id="x",
                    type="code",
                    bounding_box=BoundingBox(x=0, y=0, width=1, height=1),
                    extracted_text="for i in range(n):\n    for j in range(n):\n        print(i, j)",
                    language="python",
                    confidence=0.9,
                )
            ]
        ),
        checks=[contains("n^2"), any_of("nested", "inner loop", "outer loop")],
    ),
    EvalCase(
        name="phase1_common_misconception_correction",
        message="Isn't O(n) + O(n) just O(n^2) since we're adding two things?",
        seed=SlideSeed(),
        checks=[contains("O(n)"), not_contains("O(n^2) is correct", "yes, O(n^2)")],
    ),
    EvalCase(
        name="phase2_verified_recurrence_merge_sort",
        message="Solve this recurrence using the Master Theorem.",
        seed=SlideSeed(
            [
                SlideObject(
                    id="x",
                    type="equation",
                    bounding_box=BoundingBox(x=0, y=0, width=1, height=1),
                    extracted_text="T(n) = 2T(n/2) + n",
                    confidence=0.95,
                )
            ]
        ),
        checks=[contains("Theta(n log n)")],
    ),
    EvalCase(
        name="phase3_insertion_sort_trace",
        message="Trace insertion sort on [5, 2, 4, 6, 1, 3]",
        seed=SlideSeed(),
        checks=[contains("1, 2, 3, 4, 5, 6")],
    ),
    EvalCase(
        name="phase3_binary_search_on_sorted_array",
        message="Trace binary search on [1, 2, 3, 4, 5, 6] target = 5",
        seed=SlideSeed(),
        checks=[contains("index 4")],
    ),
    EvalCase(
        name="phase4_bfs_traversal",
        message="Run BFS starting at A",
        seed=SlideSeed(
            [
                SlideObject(
                    id="x",
                    type="graph",
                    bounding_box=BoundingBox(x=0, y=0, width=1, height=1),
                    summary="A small graph.",
                    confidence=0.9,
                    graph_structure=GraphStructure(
                        nodes=["A", "B", "C"],
                        edges=[
                            GraphEdge(node_a="A", node_b="B", direction="undirected"),
                            GraphEdge(node_a="B", node_b="C", direction="undirected"),
                        ],
                    ),
                )
            ]
        ),
        checks=[contains("A"), contains("B"), contains("C")],
    ),
    EvalCase(
        name="phase4_dijkstra_prefers_indirect_path",
        message="Find the shortest path from A using Dijkstra",
        seed=SlideSeed(
            [
                SlideObject(
                    id="x",
                    type="graph",
                    bounding_box=BoundingBox(x=0, y=0, width=1, height=1),
                    summary="A weighted graph.",
                    confidence=0.9,
                    graph_structure=GraphStructure(
                        nodes=["A", "B", "C"],
                        edges=[
                            GraphEdge(node_a="A", node_b="B", weight=4, direction="undirected"),
                            GraphEdge(node_a="A", node_b="C", weight=1, direction="undirected"),
                            GraphEdge(node_a="C", node_b="B", weight=1, direction="undirected"),
                        ],
                    ),
                )
            ]
        ),
        checks=[contains("2")],  # shortest A->B distance is 2 (via C), not the direct edge's 4
    ),
    EvalCase(
        name="phase5_simple_mode_avoids_dense_jargon_opening",
        message="What is the time complexity of this recurrence?",
        explanation_mode="simple",
        seed=SlideSeed(
            [
                SlideObject(
                    id="x",
                    type="equation",
                    bounding_box=BoundingBox(x=0, y=0, width=1, height=1),
                    extracted_text="T(n) = 2T(n/2) + n",
                    confidence=0.95,
                )
            ]
        ),
        checks=[contains("Theta(n log n)")],
    ),
    EvalCase(
        name="phase5_exam_mode_is_concise",
        message="What is the time complexity of this recurrence?",
        explanation_mode="exam",
        seed=SlideSeed(
            [
                SlideObject(
                    id="x",
                    type="equation",
                    bounding_box=BoundingBox(x=0, y=0, width=1, height=1),
                    extracted_text="T(n) = 2T(n/2) + n",
                    confidence=0.95,
                )
            ]
        ),
        checks=[word_count_between(1, 350)],  # loose bound — catches exam mode ballooning to rigorous-mode length
    ),
    EvalCase(
        name="phase5_rigorous_mode_is_thorough",
        message="What is the time complexity of this recurrence?",
        explanation_mode="rigorous",
        seed=SlideSeed(
            [
                SlideObject(
                    id="x",
                    type="equation",
                    bounding_box=BoundingBox(x=0, y=0, width=1, height=1),
                    extracted_text="T(n) = 2T(n/2) + n",
                    confidence=0.95,
                )
            ]
        ),
        checks=[word_count_between(80, 1000)],
    ),
    EvalCase(
        name="phase5_socratic_mode_withholds_the_answer",
        message="What is the time complexity of this recurrence?",
        explanation_mode="socratic",
        seed=SlideSeed(
            [
                SlideObject(
                    id="x",
                    type="equation",
                    bounding_box=BoundingBox(x=0, y=0, width=1, height=1),
                    extracted_text="T(n) = 2T(n/2) + n",
                    confidence=0.95,
                )
            ]
        ),
        checks=[not_contains("Theta(n log n)", "= n log n", "n log n"), ends_with_question(), word_count_between(1, 60)],
    ),
]


async def _seed_slide(seed: SlideSeed) -> tuple[str, str]:
    async with AsyncSessionLocal() as db:
        presentation = await PresentationRepository(db).create(title="eval", source_type="eval")
        slide = await SlideRepository(db).create(
            presentation_id=presentation.id,
            slide_number=1,
            image_hash=str(uuid.uuid4()),
            status="analyzed",
            summary="Eval slide.",
        )
        if seed.objects:
            await ObjectRepository(db).create_many(slide.id, seed.objects)
        await db.commit()
        return str(presentation.id), str(slide.id)


async def _ask(client: httpx.AsyncClient, presentation_id: str, slide_id: str, case: EvalCase) -> str:
    async with client.stream(
        "POST",
        f"{BASE_URL}/api/v1/chat",
        headers={"X-API-Key": API_KEY or ""},
        json={
            "presentation_id": presentation_id,
            "query_mode": "algorithm",
            "slide_id": slide_id,
            "message": case.message,
            "explanation_mode": case.explanation_mode,
        },
        timeout=60,
    ) as response:
        response.raise_for_status()
        full_text = ""
        async for line in response.aiter_lines():
            if line.startswith("data: ") and '"text"' in line:
                full_text += json.loads(line.removeprefix("data: ")).get("text", "")
        return full_text


async def run() -> int:
    if not API_KEY:
        print("LOCAL_API_KEY not set (env var or backend/.env) — cannot authenticate to the backend.")
        return 1

    total = 0
    passed = 0
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{BASE_URL}/api/v1/health", timeout=10)
            health.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"Backend not reachable at {BASE_URL}: {exc}")
            return 1

        for case in CASES:
            presentation_id, slide_id = await _seed_slide(case.seed)
            try:
                answer = await _ask(client, presentation_id, slide_id, case)
            except httpx.HTTPError as exc:
                print(f"[ERROR] {case.name}: request failed — {exc}")
                total += 1
                continue

            case_results = [check(answer) for check in case.checks]
            case_passed = all(ok for ok, _ in case_results)
            total += 1
            passed += int(case_passed)
            status = "PASS" if case_passed else "FAIL"
            print(f"[{status}] {case.name}")
            if not case_passed:
                for ok, reason in case_results:
                    if not ok:
                        print(f"    - {reason}")
                snippet = answer[:300].replace("\n", " ")
                print(f"    response snippet: {snippet}...")

    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
