"""Tests for POST /chat (docs/API_CONTRACT.md §3). Uses the `client` fixture
from conftest.py, which already overrides get_chat_service with
FakeChatService — no real provider API is ever called."""

import io
import json
import uuid

from conftest import FakeChatService
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import BoundingBox, GraphEdge, GraphStructure, SlideObject
from app.repositories.objects import ObjectRepository

_HEADERS = {"X-API-Key": "test-api-key"}


def _fake_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


async def _analyze_slide(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", _fake_png_bytes(), "image/png")},
        data={"slide_number": "1"},
        headers=_HEADERS,
    )
    assert response.status_code == 200
    return response.json()


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parses the raw SSE body into a list of (event_name, data_dict) pairs."""
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.strip().splitlines()
        event_name = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data_line = next(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        events.append((event_name, json.loads(data_line)))
    return events


async def test_chat_figure_mode_streams_answer(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)
    object_id = analysis["objects"][0]["id"]

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "figure",
            "slide_id": analysis["slide_id"],
            "object_id": object_id,
            "message": "What is this?",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    deltas = [data["text"] for name, data in events if name == "delta"]
    assert deltas == ["Fake ", "answer."]
    done_events = [data for name, data in events if name == "done"]
    assert len(done_events) == 1
    assert done_events[0]["referenced_object_ids"] == [object_id]
    assert done_events[0]["usage"]["input_tokens"] == 10
    assert "conversation_id" in done_events[0]
    assert "message_id" in done_events[0]


async def test_chat_slide_mode_streams_answer(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "slide",
            "slide_id": analysis["slide_id"],
            "message": "Summarize this slide.",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    done_events = [data for name, data in events if name == "done"]
    assert len(done_events) == 1
    assert done_events[0]["referenced_object_ids"] == [analysis["objects"][0]["id"]]


async def test_chat_algorithm_mode_streams_answer(client: AsyncClient) -> None:
    """Milestone: docs/AlgorithmsMVP.md Phase 1 — "algorithm" mode reuses
    the "slide" context builder (same referenced_object_ids behavior) but
    with an algorithms-aware prompt."""
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "algorithm",
            "slide_id": analysis["slide_id"],
            "message": "Why is this O(n log n)?",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    done_events = [data for name, data in events if name == "done"]
    assert len(done_events) == 1
    assert done_events[0]["referenced_object_ids"] == [analysis["objects"][0]["id"]]


async def test_chat_algorithm_mode_injects_verified_recurrence_analysis(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """docs/AlgorithmsMVP.md Phase 2: when a slide has a recurrence object,
    "algorithm" mode's context must include the deterministic Master
    Theorem result (recurrence_solver.py) — not just leave complexity
    verification entirely to the chat model."""
    analysis = await _analyze_slide(client)
    slide_id = analysis["slide_id"]

    recurrence_object = SlideObject(
        id="unused-placeholder-id",  # ObjectRepository.create_many mints its own id
        type="equation",
        bounding_box=BoundingBox(x=0.1, y=0.1, width=0.5, height=0.1),
        extracted_text="T(n) = 2T(n/2) + n",
        latex=r"T(n) = 2T\left(\frac{n}{2}\right) + n",
        confidence=0.95,
    )
    await ObjectRepository(db_session).create_many(uuid.UUID(slide_id), [recurrence_object])
    await db_session.commit()

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "algorithm",
            "slide_id": slide_id,
            "message": "Why is this O(n log n)?",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    assert FakeChatService.captured_system_prompts, "chat_service.stream_chat was never called"
    system_prompt = FakeChatService.captured_system_prompts[-1]
    assert "Verified recurrence analysis" in system_prompt
    assert "Master Theorem case: case_2" in system_prompt
    assert "Θ(n log n)" in system_prompt


async def test_chat_algorithm_mode_socratic_withholds_verified_recurrence_analysis(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Regression test: an earlier revision merely relabeled the verified
    block "ANSWER KEY — DO NOT REVEAL YET" instead of omitting it, but a
    live test showed the model narrated the full derivation anyway once
    the numeric answer was sitting in context, regardless of the label.
    Socratic mode now withholds the verified recurrence block entirely —
    the only fix that reliably worked — at the cost of the verification
    safety net for that turn."""
    analysis = await _analyze_slide(client)
    slide_id = analysis["slide_id"]

    recurrence_object = SlideObject(
        id="unused-placeholder-id",
        type="equation",
        bounding_box=BoundingBox(x=0.1, y=0.1, width=0.5, height=0.1),
        extracted_text="T(n) = 2T(n/2) + n",
        confidence=0.95,
    )
    await ObjectRepository(db_session).create_many(uuid.UUID(slide_id), [recurrence_object])
    await db_session.commit()

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "algorithm",
            "slide_id": slide_id,
            "message": "Why is this O(n log n)?",
            "explanation_mode": "socratic",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    system_prompt = FakeChatService.captured_system_prompts[-1]
    # The prompt template itself mentions "Verified recurrence analysis"
    # when describing how to use one, so check for the injected block's
    # own content (only present when the block is actually built) instead.
    assert "Master Theorem case: case_2" not in system_prompt
    assert "recursion tree:" not in system_prompt


async def test_chat_algorithm_mode_injects_verified_trace_from_message(client: AsyncClient) -> None:
    """docs/AlgorithmsMVP.md Phase 3: when the student's own message names
    a catalog algorithm and an input array, "algorithm" mode's context
    must include the verified execution trace (algorithm_tracer.py) —
    detection doesn't require the array to be on the slide itself."""
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "algorithm",
            "slide_id": analysis["slide_id"],
            "message": "Trace insertion sort on [5, 2, 4, 6, 1, 3]",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    assert FakeChatService.captured_system_prompts, "chat_service.stream_chat was never called"
    system_prompt = FakeChatService.captured_system_prompts[-1]
    assert "Verified algorithm trace" in system_prompt
    assert "result: [1, 2, 3, 4, 5, 6]" in system_prompt


async def test_chat_algorithm_mode_without_recognized_algorithm_or_array_omits_trace_block(
    client: AsyncClient,
) -> None:
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "algorithm",
            "slide_id": analysis["slide_id"],
            "message": "Explain this slide",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    system_prompt = FakeChatService.captured_system_prompts[-1]
    # The prompt template itself mentions "Verified algorithm trace" when
    # describing how to use one, so check for the injected block's own
    # marker text instead of that phrase.
    assert "computed exactly by actually running the algorithm" not in system_prompt


async def test_chat_algorithm_mode_injects_verified_graph_traversal(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """docs/AlgorithmsMVP.md Phase 4: when a slide has a graph object and
    the student asks for a BFS/DFS traversal, "algorithm" mode's context
    must include the deterministic visit order (graph_algorithm_tracer.py)."""
    analysis = await _analyze_slide(client)
    slide_id = analysis["slide_id"]

    graph_object = SlideObject(
        id="unused-placeholder-id",
        type="graph",
        bounding_box=BoundingBox(x=0.1, y=0.1, width=0.8, height=0.6),
        summary="A small undirected graph.",
        confidence=0.9,
        graph_structure=GraphStructure(
            nodes=["A", "B", "C"],
            edges=[
                GraphEdge(node_a="A", node_b="B", direction="undirected"),
                GraphEdge(node_a="B", node_b="C", direction="undirected"),
            ],
        ),
    )
    await ObjectRepository(db_session).create_many(uuid.UUID(slide_id), [graph_object])
    await db_session.commit()

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "algorithm",
            "slide_id": slide_id,
            "message": "Run BFS starting at A",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    system_prompt = FakeChatService.captured_system_prompts[-1]
    assert "Verified graph traversal" in system_prompt
    assert "BFS visit order: A -> B -> C" in system_prompt
    assert "graph_nodes: A, B, C" in system_prompt


async def test_chat_algorithm_mode_injects_verified_dijkstra_distances(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """docs/AlgorithmsMVP.md Phase 4 extension: Dijkstra's shortest-path
    distances must come from actually running the algorithm
    (graph_algorithm_tracer.py), not the chat model's own reasoning."""
    analysis = await _analyze_slide(client)
    slide_id = analysis["slide_id"]

    graph_object = SlideObject(
        id="unused-placeholder-id",
        type="graph",
        bounding_box=BoundingBox(x=0.1, y=0.1, width=0.8, height=0.6),
        summary="A small weighted graph.",
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
    await ObjectRepository(db_session).create_many(uuid.UUID(slide_id), [graph_object])
    await db_session.commit()

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "algorithm",
            "slide_id": slide_id,
            "message": "Find the shortest path from A using Dijkstra",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    system_prompt = FakeChatService.captured_system_prompts[-1]
    assert "Verified graph traversal" in system_prompt
    # A->B direct is 4, but A->C->B (1+1=2) is shorter — confirms the
    # verified block reflects the indirect path, not the direct edge.
    assert "B=2" in system_prompt


async def test_chat_algorithm_mode_explanation_mode_appends_instruction(client: AsyncClient) -> None:
    """docs/AlgorithmsMVP.md Phase 5: a non-default explanation_mode must
    append its instruction block to the algorithm-mode system prompt."""
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "algorithm",
            "slide_id": analysis["slide_id"],
            "message": "Explain this",
            "explanation_mode": "socratic",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    system_prompt = FakeChatService.captured_system_prompts[-1]
    assert "## Explanation mode: socratic" in system_prompt
    assert "Ask exactly one guiding question" in system_prompt


async def test_chat_algorithm_mode_default_explanation_mode_is_a_no_op(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "algorithm",
            "slide_id": analysis["slide_id"],
            "message": "Explain this",
        },
        headers=_HEADERS,
    )

    assert response.status_code == 200
    system_prompt = FakeChatService.captured_system_prompts[-1]
    assert "## Explanation mode" not in system_prompt


async def test_chat_figure_mode_requires_object_id(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "figure",
            "slide_id": analysis["slide_id"],
            "message": "What is this?",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 400


async def test_chat_rejects_unsupported_query_mode(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "presentation",
            "message": "What is this deck about?",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 400


async def test_chat_rejects_unknown_object_id(client: AsyncClient) -> None:
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "figure",
            "slide_id": analysis["slide_id"],
            "object_id": "00000000-0000-0000-0000-000000000000",
            "message": "What is this?",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 404


async def test_chat_rejects_unknown_presentation_id(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": "00000000-0000-0000-0000-000000000000",
            "query_mode": "slide",
            "slide_id": "00000000-0000-0000-0000-000000000000",
            "message": "hi",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 404


async def test_chat_requires_api_key(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={"query_mode": "slide", "message": "hi"},
    )
    assert response.status_code == 401


async def test_analyze_same_image_second_presentation_does_not_collide_on_object_ids(client: AsyncClient) -> None:
    """Regression test: the same image analyzed under two different
    presentations is a cache hit (image-hash cache is global), but each
    presentation's Slide row needs its own objects rows — this must not
    raise a primary-key collision (see ObjectRepository's docstring)."""
    image_bytes = _fake_png_bytes()

    first = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", image_bytes, "image/png")},
        data={"slide_number": "1"},
        headers=_HEADERS,
    )
    second = await client.post(
        "/api/v1/slides/analyze",
        files={"image": ("slide.png", image_bytes, "image/png")},
        data={"slide_number": "1"},
        headers=_HEADERS,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second.json()["objects"][0]["id"] != first.json()["objects"][0]["id"]


async def test_chat_model_field_matching_default_is_a_no_op(client: AsyncClient) -> None:
    # FakeChatService.model_name == "fake-chat-model" (tests/backend/
    # conftest.py's override). Sending that back as `model` must behave
    # identically to omitting the field entirely.
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "slide",
            "slide_id": analysis["slide_id"],
            "message": "What is this?",
            "model": "fake-chat-model",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[-1][0] == "done"


async def test_chat_model_override_without_openai_backend_is_rejected(client: AsyncClient) -> None:
    # The active chat service under test is FakeChatService, not
    # OpenAIChatService — requesting a different real model must be
    # rejected (422), never silently ignored or allowed to construct a
    # real OpenAI client with no key configured.
    analysis = await _analyze_slide(client)

    response = await client.post(
        "/api/v1/chat",
        json={
            "presentation_id": analysis["presentation_id"],
            "query_mode": "slide",
            "slide_id": analysis["slide_id"],
            "message": "What is this?",
            "model": "gpt-4o-mini",
        },
        headers=_HEADERS,
    )
    assert response.status_code == 422
