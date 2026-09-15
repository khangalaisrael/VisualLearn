"""Deterministic (non-LLM) BFS/DFS/Dijkstra tracing over a slide's
already-extracted `GraphStructure` (docs/AlgorithmsMVP.md Phase 4,
docs/TheoryOfAlgorithm.md §13). Unlike algorithm_tracer.py's sorting
catalog, the graph itself doesn't need regex-detecting from text —
`GraphStructure` is already produced by the hybrid VLM + computer-vision
pipeline (graph_topology.py, ADR-010) at slide-analyze time. This module
only needs to run the traversal and detect which one + which start node
the student is asking about.

Same "actually run it, don't trust the model to simulate it" discipline
as recurrence_solver.py and algorithm_tracer.py.
"""

from __future__ import annotations

import heapq
import re
from collections import deque
from dataclasses import dataclass

from app.models.schemas import GraphEdge


@dataclass
class GraphTraceResult:
    algorithm: str  # "bfs" | "dfs" | "dijkstra"
    start: str
    order: list[str]
    steps: list[str]
    # Only populated for "dijkstra" — shortest known distance from `start`
    # to each reachable node, in the same units as the edge weights.
    distances: dict[str, float] | None = None


def _adjacency(nodes: list[str], edges: list[GraphEdge]) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {n: [] for n in nodes}
    for edge in edges:
        if edge.node_a not in adjacency or edge.node_b not in adjacency:
            continue  # edge references a node the graph doesn't have — skip rather than crash
        if edge.direction in ("a_to_b", "bidirectional", "undirected"):
            adjacency[edge.node_a].append(edge.node_b)
        if edge.direction in ("b_to_a", "bidirectional", "undirected"):
            adjacency[edge.node_b].append(edge.node_a)
    # Sorted neighbor order makes the trace deterministic and reproducible
    # regardless of the order edges happened to be extracted in.
    for node in adjacency:
        adjacency[node] = sorted(set(adjacency[node]))
    return adjacency


def trace_bfs(nodes: list[str], edges: list[GraphEdge], start: str) -> GraphTraceResult | None:
    if start not in nodes:
        return None
    adjacency = _adjacency(nodes, edges)
    visited = {start}
    order = [start]
    queue: deque[str] = deque([start])
    steps = [f"enqueue {start} (start node), visited = {{{start}}}"]
    while queue:
        current = queue.popleft()
        steps.append(f"dequeue {current}")
        for neighbor in adjacency.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                order.append(neighbor)
                queue.append(neighbor)
                steps.append(f"  discover {neighbor} via edge {current}->{neighbor}, enqueue")
    steps.append(f"BFS visit order: {' -> '.join(order)}")
    return GraphTraceResult("bfs", start, order, steps)


def _weighted_adjacency(nodes: list[str], edges: list[GraphEdge]) -> dict[str, list[tuple[str, float]]] | None:
    """Like `_adjacency`, but keeps each edge's weight — returns None if
    any edge connecting two known nodes has no weight, since Dijkstra's
    result would be meaningless (or silently wrong) built on a mix of real
    and made-up weights. Never guesses a weight."""
    adjacency: dict[str, list[tuple[str, float]]] = {n: [] for n in nodes}
    for edge in edges:
        if edge.node_a not in adjacency or edge.node_b not in adjacency:
            continue
        if edge.weight is None:
            return None
        if edge.direction in ("a_to_b", "bidirectional", "undirected"):
            adjacency[edge.node_a].append((edge.node_b, edge.weight))
        if edge.direction in ("b_to_a", "bidirectional", "undirected"):
            adjacency[edge.node_b].append((edge.node_a, edge.weight))
    for node in adjacency:
        adjacency[node] = sorted(set(adjacency[node]))
    return adjacency


def trace_dijkstra(nodes: list[str], edges: list[GraphEdge], start: str) -> GraphTraceResult | None:
    if start not in nodes:
        return None
    adjacency = _weighted_adjacency(nodes, edges)
    if adjacency is None:
        return None

    distances: dict[str, float] = dict.fromkeys(nodes, float("inf"))
    distances[start] = 0.0
    settled: set[str] = set()
    order: list[str] = []
    steps = [f"distances initialized: {start}=0, all others=infinity"]
    heap: list[tuple[float, str]] = [(0.0, start)]

    while heap:
        dist, current = heapq.heappop(heap)
        if current in settled:
            continue
        settled.add(current)
        order.append(current)
        steps.append(f"settle {current} with shortest distance {_fmt_num(dist)}")
        for neighbor, weight in adjacency.get(current, []):
            if neighbor in settled:
                continue
            candidate = dist + weight
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                heapq.heappush(heap, (candidate, neighbor))
                steps.append(
                    f"  relax edge {current}->{neighbor} (weight {_fmt_num(weight)}): "
                    f"distance to {neighbor} improved to {_fmt_num(candidate)}"
                )
            else:
                steps.append(
                    f"  edge {current}->{neighbor} (weight {_fmt_num(weight)}): "
                    f"{_fmt_num(candidate)} is not better than current {_fmt_num(distances[neighbor])}, skip"
                )

    reachable = {n: d for n, d in distances.items() if d != float("inf")}
    steps.append(
        "final shortest distances from "
        + start
        + ": "
        + ", ".join(f"{n}={_fmt_num(d)}" for n, d in sorted(reachable.items()))
    )
    return GraphTraceResult("dijkstra", start, order, steps, distances=reachable)


def _fmt_num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def trace_dfs(nodes: list[str], edges: list[GraphEdge], start: str) -> GraphTraceResult | None:
    if start not in nodes:
        return None
    adjacency = _adjacency(nodes, edges)
    visited: set[str] = set()
    order: list[str] = []
    steps: list[str] = []

    def visit(node: str, depth: int) -> None:
        visited.add(node)
        order.append(node)
        indent = "  " * depth
        steps.append(f"{indent}visit {node}")
        for neighbor in adjacency.get(node, []):
            if neighbor in visited:
                steps.append(f"{indent}  edge {node}->{neighbor}: already visited, skip")
            else:
                steps.append(f"{indent}  edge {node}->{neighbor}: unvisited, recurse")
                visit(neighbor, depth + 1)

    visit(start, 0)
    steps.append(f"DFS visit order: {' -> '.join(order)}")
    return GraphTraceResult("dfs", start, order, steps)


_ALGORITHM_KEYWORDS = {
    "bfs": ["bfs", "breadth-first", "breadth first"],
    "dfs": ["dfs", "depth-first", "depth first"],
    "dijkstra": ["dijkstra", "shortest path"],
}
_START_NODE_PATTERN = re.compile(
    r"(?:starting\s+(?:at|from)|start\s+(?:node|at|from)|from)\s+([A-Za-z][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def find_graph_algorithm(text: str) -> str | None:
    lowered = text.lower()
    for key, phrases in _ALGORITHM_KEYWORDS.items():
        if any(phrase in lowered for phrase in phrases):
            return key
    return None


def find_start_node(text: str, nodes: list[str]) -> str | None:
    """Looks for an explicit "from X" / "starting at X" mention that names
    one of `nodes` (case-insensitive); returns the exact `nodes` spelling
    if found, else None (caller decides whether to default)."""
    match = _START_NODE_PATTERN.search(text)
    if not match:
        return None
    candidate = match.group(1)
    for node in nodes:
        if node.lower() == candidate.lower():
            return node
    return None


def trace(algorithm_key: str, nodes: list[str], edges: list[GraphEdge], start: str) -> GraphTraceResult | None:
    if algorithm_key == "bfs":
        return trace_bfs(nodes, edges, start)
    if algorithm_key == "dfs":
        return trace_dfs(nodes, edges, start)
    if algorithm_key == "dijkstra":
        return trace_dijkstra(nodes, edges, start)
    return None
