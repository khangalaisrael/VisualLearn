"""Tests for backend/app/services/graph_algorithm_tracer.py — deterministic
BFS/DFS over a slide's extracted GraphStructure (docs/AlgorithmsMVP.md
Phase 4). Pure function tests, no DB/app fixtures needed."""

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
