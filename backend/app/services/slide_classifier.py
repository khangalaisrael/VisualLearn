"""SlideClassifier — a free, local look at a slide before it is sent to the
vision model, so a plain slide isn't paid for like a busy diagram.

Every slide still goes to the vision model (maths and code must be read
exactly, which OCR can't promise). What changes is how much is sent:

- "text":      only lines of text.
- "text_code": text, plus a code panel (a box of evenly spaced lines on its
               own background).
- "visual":    a diagram, graph, chart, photo or anything else drawn.

A text slide is sent smaller and read with less effort; a visual one goes at
full useful size. Anything the checks are unsure about counts as "visual",
which is exactly what every slide got before this existed, so a wrong guess
can only ever cost what it used to, never lose detail on a figure.

Pure OpenCV, no model call: a few milliseconds per slide.
"""

import logging
from typing import Literal

import cv2
import numpy as np

logger = logging.getLogger(__name__)

SlideKind = Literal["text", "text_code", "visual"]

# Image tokens grow with pixel count (about width x height / 750). Text stays
# easily legible at 1100px on the long edge; 1568px is the most the model
# makes use of, so nothing is lost by capping a visual slide there.
_TEXT_LONG_EDGE = 1100
_VISUAL_LONG_EDGE = 1568
_JPEG_QUALITY = 85

_WORK_WIDTH = 800  # classification runs on a small copy, which is plenty and fast


def _decode(image_bytes: bytes) -> np.ndarray | None:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)


def _is_code_panel(image: np.ndarray, gray: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
    """A large box is a code panel when its background is one flat colour and
    what sits on it is short, evenly spaced lines of text."""
    region = image[y : y + h, x : x + w]
    pixels = region.reshape(-1, 3) // 16  # bucket colours so anti-aliasing doesn't matter
    _, counts = np.unique(pixels, axis=0, return_counts=True)
    if counts.max() / len(pixels) < 0.6:  # no single background colour: a picture, not a panel
        return False
    background = gray[y : y + h, x : x + w]
    edges = cv2.Canny(background, 60, 180)
    rows = (edges > 0).sum(axis=1) > 2
    # Runs of rows that hold ink: text lines. Three or more, of similar height.
    runs, run = [], 0
    for has_ink in rows:
        if has_ink:
            run += 1
        elif run:
            runs.append(run)
            run = 0
    if run:
        runs.append(run)
    runs = [r for r in runs if r >= 3]
    if len(runs) < 3:
        return False
    return float(np.std(runs)) <= 0.5 * float(np.mean(runs))


def classify_slide(image_bytes: bytes) -> SlideKind:
    try:
        return _classify(image_bytes)
    except Exception:  # never let a cheap pre-check fail a capture
        logger.exception("Slide classification failed; treating the slide as visual")
        return "visual"


def _classify(image_bytes: bytes) -> SlideKind:
    image = _decode(image_bytes)
    if image is None:
        return "visual"
    height, width = image.shape[:2]
    scale = _WORK_WIDTH / width
    image = cv2.resize(image, (_WORK_WIDTH, max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Photos: lots of distinct colours spread over the slide.
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    colourful = (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 50)
    if colourful.mean() > 0.25:
        return "visual"

    # Long straight lines: axes, arrows, diagram edges, table rules.
    edges = cv2.Canny(gray, 60, 180)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=int(width * 0.15), maxLineGap=4)
    long_lines = 0 if lines is None else len(lines)

    # Slanted strokes: tree and graph edges, arrows. Text never makes these at
    # this length, and thin lines are easy to miss as "large shapes" below.
    short = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30, minLineLength=int(width * 0.04), maxLineGap=2)
    slanted = 0
    for x1, y1, x2, y2 in [] if short is None else short[:, 0]:
        angle = abs(np.degrees(np.arctan2(int(y2) - int(y1), int(x2) - int(x1)))) % 180
        if 15 < angle < 75 or 105 < angle < 165:
            slanted += 1
    if slanted >= 3:
        return "visual"

    # Ink blobs: smear characters into words and lines, then look at the shapes.
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    words = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3)))
    contours, _ = cv2.findContours(words, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    has_code = False
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h <= height * 0.07:  # a word or a line of text
            continue
        if w * h < width * height * 0.01:  # a big letter, a bullet, a small icon
            continue
        if _is_code_panel(image, gray, x, y, w, h):
            has_code = True
            continue
        return "visual"  # something large that isn't text: a figure

    # A code panel's own border gives a few long lines; more than that is a drawing.
    if long_lines > (8 if has_code else 4):
        return "visual"
    return "text_code" if has_code else "text"


def prepare_image(image_bytes: bytes, kind: SlideKind) -> tuple[bytes, str | None]:
    """The image to actually send, and its media type (None = unchanged, so
    the caller detects it as before). Text slides are capped smaller and
    sent as JPEG; visual ones are only capped at the model's useful maximum."""
    long_edge = _VISUAL_LONG_EDGE if kind == "visual" else _TEXT_LONG_EDGE
    image = _decode(image_bytes)
    if image is None:
        return image_bytes, None
    height, width = image.shape[:2]
    factor = long_edge / max(height, width)
    if factor >= 1 and kind == "visual":
        return image_bytes, None
    if factor < 1:
        image = cv2.resize(image, (int(width * factor), int(height * factor)), interpolation=cv2.INTER_AREA)
    if kind == "visual":
        ok, encoded = cv2.imencode(".png", image)
        return (encoded.tobytes(), "image/png") if ok else (image_bytes, None)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
    return (encoded.tobytes(), "image/jpeg") if ok else (image_bytes, None)
