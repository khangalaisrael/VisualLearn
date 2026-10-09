"""Classical computer-vision graph topology extraction.

See docs/adr/ADR-010-hybrid-graph-structure-extraction.md. The vision
model (ClaudeVLMAnalyzer / OpenAIVLMAnalyzer) is asked to locate each
node's approximate center + radius and each weight annotation's value +
position — bounding-box localization and text reading are tasks vision
models handle reliably, but "approximate" is doing real work in that
sentence: live testing measured VLM center-estimate error ranging from
~40-60px up to ~160px in an 800x500 image (varies call to call, not a
fixed bias), enough to make a naive straight-line pixel-sampling test miss
the actual drawn line entirely.

Every node position is therefore refined before any connectivity test
runs (see `refine_node_positions`), via Hough circle detection over the
*whole* image rather than a small window around each VLM guess. A
windowed search was tried first and rejected: sizing the window as a
multiple of the reported radius means it stops working the moment the
model's guess is off by more than that multiple — which live testing
showed happens (a ~160px miss against a ~120px window silently fell back
to the bad raw guess). Detecting all circles once, image-wide, and then
greedily assigning each VLM guess to its nearest still-unclaimed detected
circle (nearest-first-unique, the same pattern used for weight-label
assignment below) has no such cap: it succeeds as long as the true circle
is found anywhere in the image, regardless of how far off the guess was.

Once positions are refined, this module answers the one question that
measured ~50-75% accuracy when asked of the vision model directly: "does a
line connect node A and node B?" It answers by testing every candidate
node pair and sampling pixels along the straight path between them in a
generalized (color-agnostic) edge map, instead of asking anything to
visually trace a specific line through a busy crossing region — crossings
can't confuse a test that never traces a line, only checks pixel
occupancy along a known path.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from app.models.schemas import BoundingBox, EdgeDirection, GraphEdge, GraphStructure

_MIN_LINE_FRACTION = 0.7  # fraction of sampled points that must land on an edge pixel
_SAMPLES_PER_PAIR = 40
_NODE_MARGIN_PADDING_PX = 6  # skip a few extra px past each node's reported radius
_MAX_WEIGHT_LABEL_DISTANCE_FRACTION = 0.15  # relative to image diagonal
_MAX_NODE_MATCH_DISTANCE_FRACTION = 0.35  # relative to image diagonal; generous on purpose, see module docstring
_CROP_PADDING_FRACTION = 0.3  # extra margin around an object's bounding_box, as a fraction of its size
_CROP_MIN_DIMENSION_PX = 700  # upscale target for a crop's longer side

# Candidate perpendicular bulge offsets tested between every node pair, as a
# fraction of the straight-line distance — see _find_edge_instances for why
# a family of curves is tested instead of only the straight line (bulge=0).
_CURVE_BULGE_FRACTIONS = (-0.4, -0.3, -0.2, -0.12, -0.06, -0.03, 0.0, 0.03, 0.06, 0.12, 0.2, 0.3, 0.4)
_BULGE_CLUSTER_GAP = 0.08  # qualifying bulges closer than this are treated as the same physical curve


@dataclass(frozen=True)
class RawGraphNode:
    """A node's position/size as reported by the VLM, normalized 0-1
    relative to the full slide image (same convention as BoundingBox).
    Treated as an approximate seed, not ground truth — see
    `refine_node_positions`."""

    label: str
    x: float
    y: float
    radius: float  # normalized as a fraction of image width


@dataclass(frozen=True)
class RawWeightLabel:
    value: float
    x: float
    y: float


def _decode_image(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image for graph topology detection")
    return image


_TRIM_PADDING_FRACTION = 0.12  # fixed padding re-added around the detected ink bounding box


def _trim_to_content(crop: np.ndarray) -> np.ndarray:
    """Re-crops tightly around the single largest connected cluster of
    drawn content, then re-adds a modest fixed padding.

    The object's own bounding_box (as reported by the VLM) is often looser
    than the actual diagram, and `crop_object_region`'s own padding
    compounds that — live testing found a crop where the true diagram only
    filled the right ~40% of the frame, with the rest blank. A vision
    model asked to estimate node positions *within that frame* reported
    positions far into the blank area — plausibly because a mostly-empty
    frame gives it little to calibrate "how much of this image is the
    diagram" against. Trimming to content before upscaling fixes that —
    but trimming to the bounding box of *every* non-white pixel isn't
    enough by itself: a loose crop can also catch unrelated stray marks
    (leftover title text, a caption underline) elsewhere in the frame,
    which would stretch that bounding box right back out. Taking the
    single largest connected component after a small dilation (enough to
    bridge gaps within the diagram's own lines, not enough to fuse it with
    separate stray marks) isolates the diagram specifically, since it's
    normally the largest coherent ink structure in an object's own
    bounding-box crop."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    non_white = (gray < 240).astype(np.uint8)
    dilated = cv2.dilate(non_white, np.ones((9, 9), np.uint8), iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)
    if num_labels <= 1:
        return crop

    # label 0 is the background; pick the largest foreground component by area
    largest_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = stats[largest_label, cv2.CC_STAT_LEFT : cv2.CC_STAT_LEFT + 4]

    pad_x, pad_y = int(w * _TRIM_PADDING_FRACTION), int(h * _TRIM_PADDING_FRACTION)
    height, width = crop.shape[:2]
    x0 = max(0, x - pad_x)
    y0 = max(0, y - pad_y)
    x1 = min(width, x + w + pad_x)
    y1 = min(height, y + h + pad_y)
    return crop[y0:y1, x0:x1]


def crop_object_region(image_bytes: bytes, bounding_box: BoundingBox) -> bytes:
    """Crops the full slide down to one object's region (with generous
    padding) and upscales small crops. Used before the second, focused VLM
    call that locates graph nodes/weight labels (`prompts/graph_localization.v1.md`).

    Live testing against real coursework material found two related
    real-world failures a single full-slide analysis pass couldn't avoid:
    the VLM's own node-position accuracy degraded badly when a small
    diagram had to be located within an entire busy slide (not just the
    ~40-160px error documented elsewhere in this module — errors bad
    enough to land outside the diagram entirely), and separately, small
    node icons (~15px radius) in real slides are both hard for Hough to
    detect reliably and easily confused with other circular elements
    elsewhere on the slide (bullet points, icons) that a whole-image search
    has no way to rule out. Sending a focused, upscaled crop to both the
    second VLM call and the CV step addresses both at once: there's
    nothing else on the slide left to confuse either step with, and small
    nodes become larger, clearer circles after upscaling.
    """
    image = _decode_image(image_bytes)
    height, width = image.shape[:2]

    box_x0 = bounding_box.x * width
    box_y0 = bounding_box.y * height
    box_w = bounding_box.width * width
    box_h = bounding_box.height * height
    pad_x, pad_y = box_w * _CROP_PADDING_FRACTION, box_h * _CROP_PADDING_FRACTION

    x0 = max(0, int(box_x0 - pad_x))
    y0 = max(0, int(box_y0 - pad_y))
    x1 = min(width, int(box_x0 + box_w + pad_x))
    y1 = min(height, int(box_y0 + box_h + pad_y))
    crop = image[y0:y1, x0:x1]
    crop = _trim_to_content(crop)

    crop_h, crop_w = crop.shape[:2]
    longest_side = max(crop_w, crop_h)
    if 0 < longest_side < _CROP_MIN_DIMENSION_PX:
        scale = _CROP_MIN_DIMENSION_PX / longest_side
        crop = cv2.resize(crop, (int(crop_w * scale), int(crop_h * scale)), interpolation=cv2.INTER_CUBIC)

    ok, encoded = cv2.imencode(".png", crop)
    if not ok:
        raise ValueError("Could not encode cropped region for graph localization")
    return encoded.tobytes()


def _edge_map(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 50, 150)
    # Canny marks a line's top and bottom boundary, not its filled
    # interior — for a line a few pixels thick (common after the
    # localization crop's upscaling), that leaves a real gap exactly along
    # the geometric centerline connectivity sampling sits on. A 3x3 dilate
    # wasn't enough to close it (found via live testing against a real
    # slide: a genuine edge scored 0.00 because every sample landed in
    # that centerline gap); 5x5 closes it while still being far short of
    # dilating enough to bridge genuinely separate crossing lines.
    return cv2.dilate(edges, np.ones((7, 7), np.uint8), iterations=1)


def _detect_circles(image: np.ndarray, nodes: list[RawGraphNode]) -> list[tuple[float, float, float]]:
    """Detects circular shapes once, over the whole image. Radius bounds are
    derived from the VLM's own reported radii, with generous tolerance —
    live testing against a real (JPEG, busy-slide) photo found the VLM's
    radius estimate can be off by ~2x, not just the smaller position error
    documented elsewhere in this module. A tight tolerance (previously
    0.5x-1.8x) shifts the whole search band away from the true circle size
    in that case and finds nothing; 0.3x-2.5x recovered the true node
    circles on that same image."""
    height, width = image.shape[:2]
    radii_px = [max(n.radius * width, 10) for n in nodes]
    min_radius = max(int(min(radii_px) * 0.3), 1)
    max_radius = int(max(radii_px) * 2.5)
    min_dist = max(int(float(np.median(radii_px)) * 1.3), 1)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=min_dist,
        param1=80,
        param2=25,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is None:
        return []
    return [(float(x), float(y), float(r)) for x, y, r in circles[0]]


_CONFIDENCE_RANK_PENALTY_PX = 30  # added per confidence-rank step; see _refine_positions


def _refine_positions(image: np.ndarray, nodes: list[RawGraphNode]) -> list[RawGraphNode]:
    """Matches each VLM-guessed node to a detected circle, nearest-first-
    unique on a combined score (pixel distance + a penalty per confidence
    rank step), not on raw distance alone.

    Raw distance alone can be fooled when the VLM's guess for one node
    happens to land nearer a spurious circle (title text, a stray glyph,
    or — as a unit test caught — an entirely different real node that
    isn't even in the current node list) than that node's own true
    position. Live testing hit exactly this: one node's guess was closer
    to a circular artifact in the slide's title text than to its own
    (badly mis-estimated) true position.

    Raw confidence rank alone isn't safe either: it lets a circle claim
    *some* node's slot just because it's processed first, even when that
    node's own true circle would have been a near-perfect (near-zero
    distance) match — a real node accidentally excluded from the `nodes`
    list stole a different node's slot this way in testing, purely
    because it was a strong, cleanly-detected circle.

    Combining both into one score and resolving ambiguity nearest-score-
    first (the same greedy-unique pattern used for weight-label
    assignment) gets the benefit of each: an exact or near-exact distance
    match always wins regardless of confidence rank, while confidence
    rank still breaks ties in the genuinely ambiguous cases (see module
    docstring) where distance alone would pick a spurious circle."""
    height, width = image.shape[:2]
    circles = _detect_circles(image, nodes)  # ordered by Hough confidence, strongest first
    if not circles:
        return nodes

    max_distance = (width**2 + height**2) ** 0.5 * _MAX_NODE_MATCH_DISTANCE_FRACTION
    candidates: list[tuple[float, int, int]] = []
    for node_idx, node in enumerate(nodes):
        guess_x, guess_y = node.x * width, node.y * height
        for circle_idx, (cx, cy, _cr) in enumerate(circles):
            distance = ((cx - guess_x) ** 2 + (cy - guess_y) ** 2) ** 0.5
            if distance < max_distance:
                score = distance + _CONFIDENCE_RANK_PENALTY_PX * circle_idx
                candidates.append((score, node_idx, circle_idx))
    candidates.sort(key=lambda c: c[0])

    refined = list(nodes)
    claimed_nodes: set[int] = set()
    claimed_circles: set[int] = set()
    for _score, node_idx, circle_idx in candidates:
        if node_idx in claimed_nodes or circle_idx in claimed_circles:
            continue
        cx, cy, cr = circles[circle_idx]
        refined[node_idx] = RawGraphNode(label=nodes[node_idx].label, x=cx / width, y=cy / height, radius=cr / width)
        claimed_nodes.add(node_idx)
        claimed_circles.add(circle_idx)

    return refined


def refine_node_positions(image_bytes: bytes, nodes: list[RawGraphNode]) -> list[RawGraphNode]:
    """Refines every node's position/radius. Public so callers (and tests)
    can inspect refined positions directly, not just the final topology."""
    image = _decode_image(image_bytes)
    return _refine_positions(image, nodes)


def _curve_passes_through_other_node(
    ax: float,
    ay: float,
    cx: float,
    cy: float,
    bx: float,
    by: float,
    start_t: float,
    end_t: float,
    other_nodes: list[tuple[str, float, float, float]],
) -> bool:
    """True if the candidate curve from A to B (straight, bulge=0, or
    curved) passes through some other node's own circle.

    A pair like (a, b) in an a-c-b chain, where a/c/b are drawn collinear,
    would otherwise pass this module's occupancy test: the a-b "shortcut"
    line coincides with the real a-c and c-b line segments (they're one
    visually continuous line), so it samples as fully "on" even though a-b
    isn't a drawn edge — the diagram only has a-c and c-b. Live testing hit
    this for the straight (bulge=0) case, and separately hit a curved
    variant of the same failure on a busier graph: a small-bulge candidate
    curve between two non-adjacent nodes scored a perfect contiguous run
    because it swept close enough to a third node to effectively ride the
    two real edges through it. Checking every sampled point on the actual
    candidate curve (not just the straight segment) against every other
    node's circle catches both — the curved case doesn't reduce to a
    simple point-to-segment distance since the path itself is curved."""
    for _label, nx, ny, nr in other_nodes:
        for k in range(_SAMPLES_PER_PAIR):
            t = start_t + (end_t - start_t) * k / (_SAMPLES_PER_PAIR - 1)
            px, py = _bezier_point(ax, ay, cx, cy, bx, by, t)
            distance = ((nx - px) ** 2 + (ny - py) ** 2) ** 0.5
            if distance < nr:
                return True
    return False


def _bulge_control_point(ax: float, ay: float, bx: float, by: float, bulge: float) -> tuple[float, float]:
    length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
    mid_x, mid_y = (ax + bx) / 2, (ay + by) / 2
    if length <= 0:
        return mid_x, mid_y
    perp_x, perp_y = -(by - ay) / length, (bx - ax) / length
    return mid_x + perp_x * bulge * length, mid_y + perp_y * bulge * length


def _bezier_point(ax: float, ay: float, cx: float, cy: float, bx: float, by: float, t: float) -> tuple[float, float]:
    one_minus_t = 1 - t
    x = one_minus_t**2 * ax + 2 * one_minus_t * t * cx + t**2 * bx
    y = one_minus_t**2 * ay + 2 * one_minus_t * t * cy + t**2 * by
    return x, y


_RUN_GAP_TOLERANCE = 2  # consecutive misses this short are bridged; anything longer is a real break


def _longest_run_fraction(hits: list[bool]) -> float:
    """The longest contiguous run of hits (small gaps bridged, see
    `_RUN_GAP_TOLERANCE`), as a fraction of the total sample count.

    Raw occupancy fraction alone isn't enough to tell a real drawn curve
    from a coincidence: on a busy diagram with many nearby/crossing lines,
    some candidate curve can rack up a similar overall fraction by
    skimming past *several different* real lines with gaps between them,
    never actually following one continuous stroke — live testing on the
    12-edge crossing-line stress case hit exactly this (a curve scored
    0.72 raw occupancy while its hit/miss sequence showed real gaps in the
    middle). The longest-contiguous-run metric distinguishes them: one
    real stroke gives one long run; several coincidentally-skimmed strokes
    give several short ones."""
    n = len(hits)
    filled = list(hits)
    i = 0
    while i < n:
        if not filled[i]:
            j = i
            while j < n and not filled[j]:
                j += 1
            gap_len = j - i
            if gap_len <= _RUN_GAP_TOLERANCE and i > 0 and j < n:
                for k in range(i, j):
                    filled[k] = True
            i = j
        else:
            i += 1

    best_run = 0
    current_run = 0
    for hit in filled:
        if hit:
            current_run += 1
            best_run = max(best_run, current_run)
        else:
            current_run = 0
    return best_run / n if n else 0.0


def _curve_hit_fraction(
    edge_map: np.ndarray, ax: float, ay: float, cx: float, cy: float, bx: float, by: float, start_t: float, end_t: float
) -> float:
    hits: list[bool] = []
    for k in range(_SAMPLES_PER_PAIR):
        t = start_t + (end_t - start_t) * k / (_SAMPLES_PER_PAIR - 1)
        px, py = _bezier_point(ax, ay, cx, cy, bx, by, t)
        px, py = int(round(px)), int(round(py))
        hits.append(0 <= py < edge_map.shape[0] and 0 <= px < edge_map.shape[1] and edge_map[py, px] > 0)
    return _longest_run_fraction(hits)


@dataclass(frozen=True)
class _EdgeInstance:
    """One detected edge between two nodes, including which of the tested
    candidate curves (see `_CURVE_BULGE_FRACTIONS`) matched — needed
    downstream both to locate this specific instance's midpoint (for
    weight-label assignment) and to test its two endpoints for an
    arrowhead (for direction detection)."""

    label_a: str
    label_b: str
    bulge: float
    ax: float
    ay: float
    ra: float
    bx: float
    by: float
    rb: float


def _find_edge_instances(edge_map: np.ndarray, pixel_nodes: list[tuple[str, float, float, float]]) -> list[_EdgeInstance]:
    """Tests every candidate node pair against a family of curved paths, not
    only the straight line (bulge=0), and returns one `_EdgeInstance` per
    distinct curve that qualifies.

    Real diagrams draw more than straight lines: a directed pair can be
    shown as two separate arcs bulging opposite ways (one per direction,
    each with its own weight), and even a "straight" connector can carry
    enough real curvature (live testing found ~5-9px of perpendicular
    deviation on a line that looked straight) to make bulge=0 alone miss
    it. Testing a small family of quadratic-Bezier candidate paths per
    pair — never freely tracing, so crossing lines still can't confuse
    it — catches both without reintroducing the failure mode ADR-010
    exists to avoid. Multiple qualifying bulges close together are
    clustered as one physical curve (adjacent bulge levels usually detect
    the same line); each qualifying cluster becomes a separate edge
    instance, so a bidirectional pair correctly yields two instances.
    """
    instances: list[_EdgeInstance] = []
    for i, (label_a, ax, ay, ra) in enumerate(pixel_nodes):
        for label_b, bx, by, rb in pixel_nodes[i + 1 :]:
            length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            margin_a = ra + _NODE_MARGIN_PADDING_PX
            margin_b = rb + _NODE_MARGIN_PADDING_PX
            if length <= 0 or margin_a + margin_b >= length:
                continue  # nodes overlap or are too close to sample meaningfully

            other_nodes = [n for n in pixel_nodes if n[0] not in (label_a, label_b)]
            start_t = margin_a / length
            end_t = 1 - margin_b / length

            qualifying: list[tuple[float, float]] = []  # (bulge, fraction)
            for bulge in _CURVE_BULGE_FRACTIONS:
                cx, cy = _bulge_control_point(ax, ay, bx, by, bulge)
                if _curve_passes_through_other_node(ax, ay, cx, cy, bx, by, start_t, end_t, other_nodes):
                    continue  # rides through a third node (see _curve_passes_through_other_node) — not a real direct edge
                fraction = _curve_hit_fraction(edge_map, ax, ay, cx, cy, bx, by, start_t, end_t)
                if fraction >= _MIN_LINE_FRACTION:
                    qualifying.append((bulge, fraction))
            if not qualifying:
                continue

            qualifying.sort(key=lambda q: q[0])
            clusters: list[list[tuple[float, float]]] = []
            for bulge, fraction in qualifying:
                if clusters and bulge - clusters[-1][-1][0] <= _BULGE_CLUSTER_GAP:
                    clusters[-1].append((bulge, fraction))
                else:
                    clusters.append([(bulge, fraction)])

            for cluster in clusters:
                best_bulge, _best_fraction = max(cluster, key=lambda q: q[1])
                instances.append(_EdgeInstance(label_a, label_b, best_bulge, ax, ay, ra, bx, by, rb))
    return instances


def _tangent_at(ax: float, ay: float, cx: float, cy: float, bx: float, by: float, t: float) -> tuple[float, float]:
    """Derivative of the quadratic Bezier at t — the curve's local direction of travel."""
    dx = 2 * (1 - t) * (cx - ax) + 2 * t * (bx - cx)
    dy = 2 * (1 - t) * (cy - ay) + 2 * t * (by - cy)
    return dx, dy


def _perpendicular_ink_width(edge_map: np.ndarray, x: float, y: float, tangent_x: float, tangent_y: float, max_half_width: float) -> float:
    """The width of the ink swath crossing (x, y) perpendicular to the
    curve's local direction — a plain line has a small, roughly constant
    width; an arrowhead is locally much wider. Scans outward from the
    center point along the perpendicular until two consecutive misses (to
    tolerate a single anti-aliased gap), in each direction independently."""
    tangent_length = (tangent_x**2 + tangent_y**2) ** 0.5
    if tangent_length <= 0:
        return 0.0
    perp_x, perp_y = -tangent_y / tangent_length, tangent_x / tangent_length

    half_width = 0.0
    for sign in (1, -1):
        miss_streak = 0
        for step in range(1, max(int(max_half_width), 1) + 1):
            px = int(round(x + perp_x * step * sign))
            py = int(round(y + perp_y * step * sign))
            if 0 <= py < edge_map.shape[0] and 0 <= px < edge_map.shape[1] and edge_map[py, px] > 0:
                half_width = max(half_width, step)
                miss_streak = 0
            else:
                miss_streak += 1
                if miss_streak > 1:
                    break
    return half_width * 2


# Distances from the node's own CENTER (not the connectivity margin), as a
# multiple of that node's radius, where an arrowhead's wider base typically
# sits — see _has_arrowhead's docstring for why this range specifically.
_ARROWHEAD_NEAR_RADIUS_FRACTIONS = (1.15, 1.3, 1.5, 1.7)
_ARROWHEAD_FAR_RADIUS_FRACTION = 2.5  # clearly past any arrowhead — the plain-shaft reference width
_ARROWHEAD_NARROWING_RATIO = 1.6  # how much wider a near sample must be than the far one to count as "elevated"
_ARROWHEAD_MIN_ELEVATED_SAMPLES = 2  # how many *non-closest* near samples must be elevated to call it an arrowhead


def _width_at_radius_multiple(
    edge_map: np.ndarray,
    ax: float,
    ay: float,
    cx: float,
    cy: float,
    bx: float,
    by: float,
    length: float,
    radius: float,
    radius_multiple: float,
    direction_sign: int,
) -> float:
    distance = radius_multiple * radius
    t = distance / length if direction_sign > 0 else 1 - distance / length
    t = min(max(t, 0.0), 1.0)
    x, y = _bezier_point(ax, ay, cx, cy, bx, by, t)
    tangent_x, tangent_y = _tangent_at(ax, ay, cx, cy, bx, by, t)
    return _perpendicular_ink_width(edge_map, x, y, tangent_x, tangent_y, radius * 1.2)


def _has_arrowhead(
    edge_map: np.ndarray, ax: float, ay: float, cx: float, cy: float, bx: float, by: float, length: float, radius: float, direction_sign: int
) -> bool:
    """True if ink width narrows moving away from the node — the geometric
    signature of an arrowhead (a filled triangle, wide near the node, that
    narrows down to the connecting line's constant width a short distance
    further out). A plain line has no such narrowing.

    Measured directly against a synthetic plain line and one with a real
    arrowhead: up to ~1.1x the node's own radius from its center, *both*
    profiles are identical regardless of arrowhead presence — that region
    is dominated by the node's own circle outline, not the line/arrowhead
    content, so sampling there (as an earlier version of this function
    did, anchored to the connectivity test's much closer margin) can't
    distinguish anything. The real difference only appeared from ~1.15x
    to ~1.7x radius (arrowhead: ~22-28px wide; plain line at the same
    distance: ~10-12px), which is also consistent with where a real
    arrowhead's base is typically drawn (touching the boundary at 1.0x,
    basing out a bit further). A reference sample further out (definitely
    past any arrowhead, at the plain shaft's own width) is the baseline
    the near samples are compared against.

    A real photo later found that taking the *max* of the near samples
    wasn't safe either: a plain line on that image showed one transient
    spike at exactly the closest sample (1.15x) — still an echo of the
    node's own circle boundary at that particular rendering, apparently
    lingering slightly past 1.1x for it — that a max-based check couldn't
    tell apart from a real arrowhead's sustained width across *multiple*
    near samples. Requiring at least `_ARROWHEAD_MIN_ELEVATED_SAMPLES` of
    the non-closest near samples (1.3x, 1.5x, 1.7x — excluding 1.15x,
    since that one is the most exposed to this exact false positive) to
    each independently clear the ratio threshold catches a real,
    triangle-shaped taper while ignoring a single transient blip.

    This replaced an earlier density-ratio approach that could tell "one
    end denser than the other" (a one-sided arrow) but had no way to tell
    "both ends dense" (a bidirectional arrow) apart from "neither end
    dense" (a plain line) — both looked identical under a ratio-only
    comparison. Measuring actual width narrowing at each end
    independently removes that ambiguity: a plain line's width profile is
    flat (near ≈ far) at both ends regardless of what the other end looks
    like.
    """
    far_width = _width_at_radius_multiple(edge_map, ax, ay, cx, cy, bx, by, length, radius, _ARROWHEAD_FAR_RADIUS_FRACTION, direction_sign)
    if far_width <= 0:
        return False
    elevated_count = sum(
        1
        for frac in _ARROWHEAD_NEAR_RADIUS_FRACTIONS[1:]  # skip the closest sample — most exposed to the circle-echo false positive
        if _width_at_radius_multiple(edge_map, ax, ay, cx, cy, bx, by, length, radius, frac, direction_sign) / far_width >= _ARROWHEAD_NARROWING_RATIO
    )
    return elevated_count >= _ARROWHEAD_MIN_ELEVATED_SAMPLES


def _detect_direction(edge_map: np.ndarray, instance: _EdgeInstance) -> EdgeDirection:
    """Classifies an edge instance by checking each endpoint independently
    for an arrowhead's width-narrowing signature (see `_has_arrowhead`)."""
    length = ((instance.bx - instance.ax) ** 2 + (instance.by - instance.ay) ** 2) ** 0.5
    if length <= 0:
        return "undirected"

    cx, cy = _bulge_control_point(instance.ax, instance.ay, instance.bx, instance.by, instance.bulge)
    a_has_head = _has_arrowhead(edge_map, instance.ax, instance.ay, cx, cy, instance.bx, instance.by, length, instance.ra, +1)
    b_has_head = _has_arrowhead(edge_map, instance.ax, instance.ay, cx, cy, instance.bx, instance.by, length, instance.rb, -1)

    if a_has_head and b_has_head:
        return "bidirectional"
    if a_has_head:
        return "b_to_a"  # arrowhead at A's end -> edge points into A, i.e. from B
    if b_has_head:
        return "a_to_b"
    return "undirected"


def detect_edges(image_bytes: bytes, nodes: list[RawGraphNode]) -> list[tuple[str, str]]:
    """Refines node positions, then tests every candidate pair; returns
    those judged connected as (label_a, label_b) pairs. See module
    docstring for the two-stage design; see `_find_edge_instances` for
    the curved-path family tested. Collapses multiple edge instances
    between the same pair (e.g. a bidirectional pair drawn as two arcs)
    to one entry — callers needing per-instance detail (weight, direction)
    should use `build_graph_structure` instead."""
    image = _decode_image(image_bytes)
    height, width = image.shape[:2]
    edge_map = _edge_map(image)

    refined = _refine_positions(image, nodes)
    pixel_nodes = [(n.label, n.x * width, n.y * height, n.radius * width) for n in refined]
    instances = _find_edge_instances(edge_map, pixel_nodes)
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for instance in instances:
        pair = (instance.label_a, instance.label_b)
        if pair not in seen:
            seen.add(pair)
            result.append(pair)
    return result


def _instance_midpoint(instance: _EdgeInstance) -> tuple[float, float]:
    """The midpoint of this instance's actual matched curve (not the
    straight node-to-node midpoint) — needed so weight-label matching
    picks the label near e.g. the top arc of a bidirectional pair, not the
    geometric center between the two nodes, which for a curved edge can be
    well off the drawn line itself."""
    cx, cy = _bulge_control_point(instance.ax, instance.ay, instance.bx, instance.by, instance.bulge)
    return _bezier_point(instance.ax, instance.ay, cx, cy, instance.bx, instance.by, 0.5)


def _assign_weights_uniquely(
    instances: list[_EdgeInstance],
    weight_labels: list[RawWeightLabel],
    width: int,
    height: int,
) -> dict[int, float | None]:
    """Assigns each weight label to at most one edge instance, nearest-first.

    A naive independent "nearest label" lookup per edge can assign the
    same label to two different edges — this happens for real when two
    edges cross at (or very near) the same midpoint, e.g. the two
    diagonals of a rectangle, and the vision model only detected one
    weight label near that shared point (missed the other one entirely,
    rather than misreading it — see docs/adr/ADR-010's Consequences).
    Greedy nearest-first-unique assignment means the edge actually closest
    to a given label claims it, and the other edge is left with
    `weight: None` (a correct "we don't know," not a wrong borrowed value).
    Indexed by position in `instances` (not by (label_a, label_b)) since a
    bidirectional pair can have two distinct instances needing distinct
    weights.
    """
    diagonal = (width**2 + height**2) ** 0.5
    max_distance = diagonal * _MAX_WEIGHT_LABEL_DISTANCE_FRACTION

    candidates: list[tuple[float, int, int]] = []
    for instance_idx, instance in enumerate(instances):
        mid_x, mid_y = _instance_midpoint(instance)
        for label_idx, wl in enumerate(weight_labels):
            wx, wy = wl.x * width, wl.y * height
            distance = ((wx - mid_x) ** 2 + (wy - mid_y) ** 2) ** 0.5
            if distance < max_distance:
                candidates.append((distance, instance_idx, label_idx))
    candidates.sort(key=lambda c: c[0])

    assigned: dict[int, float | None] = dict.fromkeys(range(len(instances)))
    claimed_labels: set[int] = set()
    claimed_instances: set[int] = set()
    for _distance, instance_idx, label_idx in candidates:
        if instance_idx in claimed_instances or label_idx in claimed_labels:
            continue
        assigned[instance_idx] = weight_labels[label_idx].value
        claimed_instances.add(instance_idx)
        claimed_labels.add(label_idx)

    return assigned


def build_graph_structure(
    image_bytes: bytes,
    nodes: list[RawGraphNode],
    weight_labels: list[RawWeightLabel],
) -> GraphStructure:
    image = _decode_image(image_bytes)
    height, width = image.shape[:2]
    edge_map = _edge_map(image)

    refined_nodes = _refine_positions(image, nodes)
    pixel_nodes = [(n.label, n.x * width, n.y * height, n.radius * width) for n in refined_nodes]
    instances = _find_edge_instances(edge_map, pixel_nodes)

    weights_by_instance = _assign_weights_uniquely(instances, weight_labels, width, height)
    edges = [
        GraphEdge(
            node_a=instance.label_a,
            node_b=instance.label_b,
            weight=weights_by_instance[idx],
            direction=_detect_direction(edge_map, instance),
        )
        for idx, instance in enumerate(instances)
    ]
    return GraphStructure(nodes=[n.label for n in nodes], edges=edges)
