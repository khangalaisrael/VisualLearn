"""The slide-reading quality tool's scoring (tools/quality/scoring.py): what
counts as reading a slide correctly, independent of how the maths or code
was typeset."""

import io
import sys
import uuid
from pathlib import Path

from PIL import Image

from app.models.schemas import BoundingBox, GraphEdge, GraphStructure, SlideObject

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "quality"))
from scoring import CaseScore, normalize, score_case

_BOX = BoundingBox(x=0.1, y=0.1, width=0.5, height=0.2)


def _obj(type_: str, **fields) -> SlideObject:
    return SlideObject(id=str(uuid.uuid4()), type=type_, bounding_box=_BOX, confidence=0.9, **fields)


def test_normalize_treats_latex_and_unicode_spellings_alike() -> None:
    assert normalize(r"T(n) = 2T\left(\frac{n}{2}\right) + \Theta(n)") == normalize("T(n)=2T(n/2)+Θ(n)")
    assert normalize(r"\det(A - \lambda I) = 0") == normalize("det(A − λI) = 0")
    assert normalize(r"x_1 \oplus (x_2 \oplus z)") == normalize("x₁ ⊕ (x₂ ⊕ z)")
    assert normalize("map _ []     = []") == normalize("map _ [] = []")
    assert normalize("Merge Sort") != normalize("Merge Sorts")


def test_a_correct_reading_scores_full_marks() -> None:
    case = {
        "image": "s.png",
        "types": ["title", "equation", "diagram|graph"],
        "text": ["Running Time", ["2T(n/2)", "nope"], "cn/4"],
    }
    objects = [
        _obj("title", extracted_text="Running Time of Merge Sort"),
        _obj("equation", latex=r"T(n) = 2T\left(\frac{n}{2}\right) + \Theta(n)"),
        _obj(
            "graph",
            graph_structure=GraphStructure(
                nodes=["cn", "cn/2", "cn/4"],
                edges=[GraphEdge(node_a="cn", node_b="cn/2")],
            ),
        ),
    ]
    score = score_case(case, "A recursion tree.", objects)
    assert score.score == 1.0 and score.missing == []


def test_misreadings_are_listed_and_lower_the_score() -> None:
    case = {
        "image": "code.png",
        "types": ["title", "code"],
        "text": ["Merge Sort in Python"],
        "code": {
            "language": "python",
            "lines": ["def merge_sort(a):", "mid = len(a) // 2"],
        },
    }
    objects = [
        _obj("title", extracted_text="Merge Sort in Python"),
        _obj(
            "code",
            language="python",
            extracted_text="def merge_sort(a):\n    mid = len(a) / 2",
        ),
    ]
    score = score_case(case, "", objects)
    assert score.missing == ["code 'mid = len(a) // 2'"]
    assert score.score == 4 / 5

    # In code an underscore matters, even though maths ignores it (x_1 = x₁).
    renamed = score_case(
        case,
        "",
        [
            _obj(
                "code",
                language="python",
                extracted_text="def merge sort(a):\n    mid = len(a) // 2",
            )
        ],
    )
    assert [item for item in renamed.missing if item.startswith("code")] == ["code 'def merge_sort(a):'"]


def test_code_read_as_the_wrong_language_does_not_count() -> None:
    case = {
        "image": "hs.png",
        "code": {"language": "haskell", "lines": ["map f (x:xs) = f x : map f xs"]},
    }
    score = score_case(
        case,
        "",
        [
            _obj(
                "code",
                language="python",
                extracted_text="map f (x:xs) = f x : map f xs",
            )
        ],
    )
    assert score.code_found == 0
    assert score.missing[0] == "code language haskell (read as python)"


def test_a_failed_analysis_scores_zero() -> None:
    assert CaseScore(image="x.png", types_total=3, types_found=3, error="ValueError: bad JSON").score == 0.0


def test_shrink_caps_the_longer_side() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "quality"))
    from run_eval import shrink

    buffer = io.BytesIO()
    Image.new("RGB", (2000, 1000), "white").save(buffer, format="PNG")
    small = Image.open(io.BytesIO(shrink(buffer.getvalue(), 1000)))
    assert small.size == (1000, 500)
    assert shrink(buffer.getvalue(), None) == buffer.getvalue()
    assert shrink(buffer.getvalue(), 4000) == buffer.getvalue()
