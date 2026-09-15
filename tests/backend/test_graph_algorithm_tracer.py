"""Tests for backend/app/services/graph_algorithm_tracer.py — deterministic
BFS/DFS/Dijkstra over a slide's extracted GraphStructure
(docs/AlgorithmsMVP.md Phase 4). Pure function tests, no DB/app fixtures
needed."""

import pytest

from app.models.schemas import GraphEdge
from app.services.graph_algorithm_tracer import find_graph_algorithm, find_start_node, trace

_NODES = ["A", "B", "C", "D", "E"]
_UNDIRECTED_EDGES = [
    GraphEdge(node_a="A", node_b="B", direction="undirected"),
    GraphEdge(node_a="A", node_b="C", direction="undirected"),
    GraphEdge(node_a="B", node_b="D", direction="undirected"),
    GraphEdge(node_a="C", node_b="D", direction="undirected"),
    GraphEdge(node_a="D", node_b="E", direction="undirected"),
]
_WEIGHTED_EDGES = [
    GraphEdge(node_a="A", node_b="B", weight=4, direction="undirected"),
    GraphEdge(node_a="A", node_b="C", weight=1, direction="undirected"),
    GraphEdge(node_a="C", node_b="B", weight=1, direction="undirected"),
    GraphEdge(node_a="B", node_b="D", weight=1, direction="undirected"),
    GraphEdge(node_a="C", node_b="D", weight=5, direction="undirected"),
    GraphEdge(node_a="D", node_b="E", weight=3, direction="undirected"),
]


def test_bfs_visits_in_breadth_first_order():
    result = trace("bfs", _NODES, _UNDIRECTED_EDGES, "A")
    assert result is not None
    assert result.order == ["A", "B", "C", "D", "E"]


def test_dfs_visits_in_depth_first_order():
    result = trace("dfs", _NODES, _UNDIRECTED_EDGES, "A")
    assert result is not None
    assert result.order == ["A", "B", "D", "C", "E"]


def test_directed_edges_respect_direction():
    directed_edges = [
        GraphEdge(node_a="A", node_b="B", direction="a_to_b"),
        GraphEdge(node_a="C", node_b="B", direction="a_to_b"),  # B->C not traversable
    ]
    result = trace("bfs", ["A", "B", "C"], directed_edges, "A")
    assert result is not None
    assert result.order == ["A", "B"]  # C unreachable from A via a_to_b-only edges


def test_bidirectional_edge_is_traversable_both_ways():
    edges = [GraphEdge(node_a="A", node_b="B", direction="bidirectional")]
    forward = trace("bfs", ["A", "B"], edges, "A")
    backward = trace("bfs", ["A", "B"], edges, "B")
    assert forward.order == ["A", "B"]
    assert backward.order == ["B", "A"]


def test_disconnected_nodes_are_not_visited():
    result = trace("bfs", [*_NODES, "Z"], _UNDIRECTED_EDGES, "A")
    assert result is not None
    assert "Z" not in result.order


def test_unknown_start_node_returns_none():
    assert trace("bfs", _NODES, _UNDIRECTED_EDGES, "Z") is None


def test_dijkstra_finds_correct_shortest_distances():
    # Classic example: A->B direct is 4, but A->C->B is 1+1=2, shorter.
    result = trace("dijkstra", _NODES, _WEIGHTED_EDGES, "A")
    assert result is not None
    assert result.distances == {"A": 0, "B": 2, "C": 1, "D": 3, "E": 6}


def test_dijkstra_prefers_indirect_shorter_path_over_direct_edge():
    result = trace("dijkstra", _NODES, _WEIGHTED_EDGES, "A")
    assert result is not None
    assert any("relax edge A->C" in step or "relax edge A->B" in step for step in result.steps)
    # The direct A-B edge (weight 4) must lose to the A-C-B path (1+1=2).
    assert result.distances["B"] == 2


def test_dijkstra_unreachable_node_is_excluded_from_distances():
    result = trace("dijkstra", [*_NODES, "Z"], _WEIGHTED_EDGES, "A")
    assert result is not None
    assert "Z" not in result.distances


def test_dijkstra_refuses_when_any_edge_is_unweighted():
    # docs/AlgorithmsMVP.md Phase 4: never guess a missing weight — a
    # partial or made-up weight could silently produce a wrong shortest
    # path rather than an honestly-declined one.
    edges_with_gap = [*_WEIGHTED_EDGES, GraphEdge(node_a="D", node_b="E", weight=None, direction="undirected")]
    assert trace("dijkstra", _NODES, edges_with_gap, "A") is None


@pytest.mark.parametrize(
    "text",
    ["Run Dijkstra from A", "Find the shortest path starting at A", "dijkstra's algorithm please"],
)
def test_find_graph_algorithm_recognizes_dijkstra(text):
    assert find_graph_algorithm(text) == "dijkstra"


def test_unrecognized_algorithm_returns_none():
    assert trace("dijkstra", _NODES, _UNDIRECTED_EDGES, "A") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Run BFS on this graph", "bfs"),
        ("Do a breadth-first search", "bfs"),
        ("What does DFS produce here?", "dfs"),
        ("depth first traversal please", "dfs"),
        ("Explain this slide", None),
    ],
)
def test_find_graph_algorithm(text, expected):
    assert find_graph_algorithm(text) == expected


def test_find_start_node_matches_case_insensitively():
    assert find_start_node("Run BFS starting at b", _NODES) == "B"


def test_find_start_node_ignores_names_not_in_the_graph():
    assert find_start_node("Run BFS starting at Z", _NODES) is None


def test_find_start_node_returns_none_without_a_mention():
    assert find_start_node("Run BFS on this graph", _NODES) is None
