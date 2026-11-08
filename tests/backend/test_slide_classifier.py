"""The local pre-check that decides how much of a slide to send to the vision model."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services.slide_classifier import classify_slide, prepare_image

CASES = Path(__file__).resolve().parents[2] / "tools" / "quality" / "cases"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("eigenvalues.png", "text"),
        ("haskell-map-filter.png", "text_code"),
        ("merge-sort-python.png", "text_code"),
        # A code panel beside a tree diagram: the diagram wins.
        ("haskell-foldr.png", "visual"),
        ("master-theorem-table.png", "visual"),
        ("merge-sort-recurrence.png", "visual"),
        ("merge-sort-steps.png", "visual"),
    ],
)
def test_real_slides_are_classified(name: str, expected: str) -> None:
    assert classify_slide((CASES / name).read_bytes()) == expected


def test_unreadable_image_counts_as_visual() -> None:
    assert classify_slide(b"not an image") == "visual"


def _png(width: int, height: int) -> bytes:
    ok, encoded = cv2.imencode(".png", np.full((height, width, 3), 255, dtype=np.uint8))
    assert ok
    return encoded.tobytes()


def test_text_slide_is_shrunk_to_jpeg() -> None:
    sent, media_type = prepare_image(_png(3840, 2160), "text")
    image = cv2.imdecode(np.frombuffer(sent, np.uint8), cv2.IMREAD_COLOR)
    assert media_type == "image/jpeg"
    assert max(image.shape[:2]) == 1100


def test_visual_slide_is_only_capped_at_the_models_maximum() -> None:
    sent, media_type = prepare_image(_png(3840, 2160), "visual")
    image = cv2.imdecode(np.frombuffer(sent, np.uint8), cv2.IMREAD_COLOR)
    assert media_type == "image/png"
    assert max(image.shape[:2]) == 1568


def test_small_visual_slide_is_sent_untouched() -> None:
    original = _png(1000, 600)
    assert prepare_image(original, "visual") == (original, None)
