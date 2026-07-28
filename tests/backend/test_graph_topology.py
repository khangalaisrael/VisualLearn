"""Unit tests for graph_topology.py (docs/adr/ADR-010-hybrid-graph-structure-extraction.md)."""

import io

from PIL import Image, ImageDraw

from app.services.graph_topology import RawGraphNode, RawWeightLabel, build_graph_structure, detect_edges


def _make_test_image() -> tuple[bytes, int, int]:
    """400x200 image: nodes A(60,100) and B(200,100) connected by a line;
    node C(340,100) drawn but NOT connected to either."""
    width, height = 400, 200
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    draw.line([(60, 100), (200, 100)], fill="black", width=3)
    for cx, cy in [(60, 100), (200, 100), (340, 100)]:
        draw.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill="lightblue", outline="black", width=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue(), width, height


def test_detect_edges_finds_connected_pair_and_not_disconnected_pairs() -> None:
    image_bytes, width, height = _make_test_image()
    nodes = [
        RawGraphNode(label="A", x=60 / width, y=100 / height, radius=20 / width),
        RawGraphNode(label="B", x=200 / width, y=100 / height, radius=20 / width),
        RawGraphNode(label="C", x=340 / width, y=100 / height, radius=20 / width),
    ]

    pairs = {tuple(sorted(p)) for p in detect_edges(image_bytes, nodes)}

    assert ("A", "B") in pairs
    assert ("A", "C") not in pairs
    assert ("B", "C") not in pairs


def test_build_graph_structure_assigns_nearest_weight() -> None:
    image_bytes, width, height = _make_test_image()
    nodes = [
        RawGraphNode(label="A", x=60 / width, y=100 / height, radius=20 / width),
        RawGraphNode(label="B", x=200 / width, y=100 / height, radius=20 / width),
    ]
    weight_labels = [RawWeightLabel(value=7, x=130 / width, y=100 / height)]

    structure = build_graph_structure(image_bytes, nodes, weight_labels)

    assert structure.nodes == ["A", "B"]
    assert len(structure.edges) == 1
    assert {structure.edges[0].node_a, structure.edges[0].node_b} == {"A", "B"}
    assert structure.edges[0].weight == 7


def test_build_graph_structure_no_edges_when_nodes_unconnected() -> None:
    image_bytes, width, height = _make_test_image()
    nodes = [
        RawGraphNode(label="A", x=60 / width, y=100 / height, radius=20 / width),
        RawGraphNode(label="C", x=340 / width, y=100 / height, radius=20 / width),
    ]

    structure = build_graph_structure(image_bytes, nodes, [])

    assert structure.edges == []


def test_build_graph_structure_weight_unassigned_when_no_label_nearby() -> None:
    image_bytes, width, height = _make_test_image()
    nodes = [
        RawGraphNode(label="A", x=60 / width, y=100 / height, radius=20 / width),
        RawGraphNode(label="B", x=200 / width, y=100 / height, radius=20 / width),
    ]

    structure = build_graph_structure(image_bytes, nodes, [])

    assert len(structure.edges) == 1
    assert structure.edges[0].weight is None


def _make_directed_test_image(*, arrow_at_a: bool, arrow_at_b: bool) -> tuple[bytes, int, int, int]:
    """400x200 image: nodes A(60,100) and B(200,100), connected by a line
    with an optional arrowhead at either end (or both, for a bidirectional
    edge) — arrowhead tip touches the node boundary, base a bit further out
    (see graph_topology.py's _has_arrowhead docstring for why this specific
    placement matters for detection)."""
    width, height, node_radius = 400, 200, 20
    ax, bx, y = 60, 200, 100
    tip_a_x, base_a_x = ax + node_radius, ax + node_radius + int(node_radius * 0.7)
    tip_b_x, base_b_x = bx - node_radius, bx - node_radius - int(node_radius * 0.7)

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    line_x0 = base_a_x if arrow_at_a else ax
    line_x1 = base_b_x if arrow_at_b else bx
    draw.line([(line_x0, y), (line_x1, y)], fill="black", width=3)
    if arrow_at_a:
        draw.polygon([(tip_a_x, y), (base_a_x, y - 9), (base_a_x, y + 9)], fill="black")
    if arrow_at_b:
        draw.polygon([(tip_b_x, y), (base_b_x, y - 9), (base_b_x, y + 9)], fill="black")
    draw.ellipse([ax - node_radius, y - node_radius, ax + node_radius, y + node_radius], fill="lightblue", outline="black", width=2)
    draw.ellipse([bx - node_radius, y - node_radius, bx + node_radius, y + node_radius], fill="lightblue", outline="black", width=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue(), width, height, node_radius


def _directed_test_nodes(width: int, height: int, node_radius: int) -> list[RawGraphNode]:
    return [
        RawGraphNode(label="A", x=60 / width, y=100 / height, radius=node_radius / width),
        RawGraphNode(label="B", x=200 / width, y=100 / height, radius=node_radius / width),
    ]


def test_build_graph_structure_direction_undirected_for_plain_line() -> None:
    image_bytes, width, height, node_radius = _make_directed_test_image(arrow_at_a=False, arrow_at_b=False)
    structure = build_graph_structure(image_bytes, _directed_test_nodes(width, height, node_radius), [])

    assert len(structure.edges) == 1
    assert structure.edges[0].direction == "undirected"


def test_build_graph_structure_direction_a_to_b() -> None:
    image_bytes, width, height, node_radius = _make_directed_test_image(arrow_at_a=False, arrow_at_b=True)
    structure = build_graph_structure(image_bytes, _directed_test_nodes(width, height, node_radius), [])

    assert len(structure.edges) == 1
    assert structure.edges[0].direction == "a_to_b"


def test_build_graph_structure_direction_b_to_a() -> None:
    image_bytes, width, height, node_radius = _make_directed_test_image(arrow_at_a=True, arrow_at_b=False)
    structure = build_graph_structure(image_bytes, _directed_test_nodes(width, height, node_radius), [])

    assert len(structure.edges) == 1
    assert structure.edges[0].direction == "b_to_a"


def test_build_graph_structure_direction_bidirectional() -> None:
    image_bytes, width, height, node_radius = _make_directed_test_image(arrow_at_a=True, arrow_at_b=True)
    structure = build_graph_structure(image_bytes, _directed_test_nodes(width, height, node_radius), [])

    assert len(structure.edges) == 1
    assert structure.edges[0].direction == "bidirectional"
