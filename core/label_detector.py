"""Page-size classification and detection of several labels on one page.

Labels are located by an XY-cut over the page's text words, images and vector
drawings. A split is only accepted when every resulting region looks like a
complete label; otherwise the caller keeps the page whole and flags it.
Nothing here modifies a PDF.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from core import config
from core.models import Box


class SizeClass(str, Enum):
    LABEL_4X6 = "4x6"
    A4 = "A4"
    OTHER = "other"


def classify_size(width: float, height: float, tol: float = config.SIZE_TOLERANCE_PT) -> SizeClass:
    short, long_ = sorted((width, height))
    if abs(short - config.LABEL_W) <= tol and abs(long_ - config.LABEL_H) <= tol:
        return SizeClass.LABEL_4X6
    if abs(short - config.A4_SHORT) <= tol and abs(long_ - config.A4_LONG) <= tol:
        return SizeClass.A4
    return SizeClass.OTHER


def describe_size(width: float, height: float, size_class: SizeClass) -> str:
    inches = f"{width / 72:.2f} x {height / 72:.2f} in ({width:.0f} x {height:.0f} pt)"
    if size_class is SizeClass.A4:
        return f"A4 page, {inches}"
    return f"Non-standard page size {inches}"


def crop_is_safe(page) -> tuple[bool, str]:
    """True when set_cropbox() coordinates equal the coordinates used for detection."""
    if page.rotation != 0:
        return False, f"page is rotated {page.rotation} degrees"
    mb, rect = page.mediabox, page.rect
    if abs(mb.x0) > 0.01 or abs(mb.y0) > 0.01:
        return False, "MediaBox does not start at 0,0"
    if abs(rect.width - mb.width) > 0.5 or abs(rect.height - mb.height) > 0.5:
        return False, "page already has a smaller CropBox"
    return True, ""


# --------------------------------------------------------------------------
# Elements and helpers
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Element:
    box: Box
    kind: str  # "w" word, "i" image, "d" drawing


def _union(els: Sequence[Element]) -> Box:
    return (min(e.box[0] for e in els), min(e.box[1] for e in els),
            max(e.box[2] for e in els), max(e.box[3] for e in els))


def _size(box: Box) -> tuple[float, float]:
    return box[2] - box[0], box[3] - box[1]


def _intersects(a: Box, b: Box) -> bool:
    return min(a[2], b[2]) - max(a[0], b[0]) > 1.0 and min(a[3], b[3]) - max(a[1], b[1]) > 1.0


def _contains(outer: Box, inner: Box, eps: float = 0.01) -> bool:
    return (outer[0] <= inner[0] + eps and outer[1] <= inner[1] + eps
            and outer[2] >= inner[2] - eps and outer[3] >= inner[3] - eps)


def collect_elements(page, words=None) -> list[Element]:
    """Gather the visible building blocks of a page (read-only). ``words`` may be passed in when
    the caller already extracted them (saves a second text extraction)."""
    rect = page.rect
    page_area = max(rect.width * rect.height, 1.0)
    els: list[Element] = []
    for w in (words if words is not None else page.get_text("words")):
        els.append(Element((float(w[0]), float(w[1]), float(w[2]), float(w[3])), "w"))
    for info in page.get_image_info():
        b = info["bbox"]
        els.append(Element((float(b[0]), float(b[1]), float(b[2]), float(b[3])), "i"))
    for d in page.get_drawings():
        r = d["rect"]
        box = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
        w, h = _size(box)
        if w * h >= config.BACKGROUND_COVER_FRACTION * page_area:
            continue  # page-sized background
        thin = min(w, h) <= config.SEPARATOR_MAX_THICKNESS_PT
        long_span = max(w / max(rect.width, 1.0), h / max(rect.height, 1.0))
        if thin and long_span >= config.SEPARATOR_MIN_SPAN_FRACTION:
            continue  # cut line between labels
        els.append(Element(box, "d"))
    return els


def _label_like(els: Sequence[Element]) -> bool:
    if not els:
        return False
    w, h = _size(_union(els))
    short, long_ = sorted((w, h))
    if short < config.LABEL_MIN_SHORT_PT or long_ < config.LABEL_MIN_LONG_PT:
        return False
    words = sum(1 for e in els if e.kind == "w")
    return words >= config.LABEL_MIN_WORDS or any(e.kind == "i" for e in els)


def _is_noise(els: Sequence[Element]) -> bool:
    """A footer/header scrap: a few words, no images, small area."""
    if not els or any(e.kind == "i" for e in els):
        return False
    words = sum(1 for e in els if e.kind == "w")
    w, h = _size(_union(els))
    return words <= config.NOISE_MAX_WORDS and w * h <= config.NOISE_MAX_AREA_FACTOR * config.LABEL_W * config.LABEL_H


def _gaps(els: Sequence[Element], axis: int, min_gap: float) -> list[tuple[float, float]]:
    ivs = sorted((e.box[axis], e.box[axis + 2]) for e in els)
    gaps: list[tuple[float, float]] = []
    end = ivs[0][1]
    for start, stop in ivs[1:]:
        if start - end >= min_gap:
            gaps.append((end, start))
        end = max(end, stop)
    return gaps


def _cut(els: list[Element], allow_trim: bool = True) -> list[list[Element]]:
    """Recursively split ``els`` into label-like groups."""
    if len(els) < 2:
        return [els]
    best = None   # widest gap where both sides look like labels
    trim = None   # widest gap where one side is a label and the other is noise
    for axis in (0, 1):
        for g0, g1 in _gaps(els, axis, config.MIN_GAP_PT):
            mid = (g0 + g1) / 2
            low = [e for e in els if e.box[axis + 2] <= mid]
            high = [e for e in els if e.box[axis] >= mid]
            width = g1 - g0
            low_ok, high_ok = _label_like(low), _label_like(high)
            if low_ok and high_ok:
                if best is None or width > best[0]:
                    best = (width, low, high)
            elif allow_trim and low_ok and _is_noise(high):
                if trim is None or width > trim[0]:
                    trim = (width, low)
            elif allow_trim and high_ok and _is_noise(low):
                if trim is None or width > trim[0]:
                    trim = (width, high)
    if best is not None:
        return _cut(best[1]) + _cut(best[2])
    if trim is not None:
        trimmed = _cut(trim[1], allow_trim=True)
        if len(trimmed) >= 2:      # only drop the noise if it exposes several labels
            return trimmed
    return [els]


def _snap(content: Box, page: Box, others: Sequence[Box]) -> Box:
    """Crop rectangle for one label: exactly 4x6 when it fits, else content + padding."""
    cw, ch = _size(content)
    portrait = ch >= cw
    tw, th = (config.LABEL_W, config.LABEL_H) if portrait else (config.LABEL_H, config.LABEL_W)
    pw, ph = _size(page)
    if cw <= tw + 0.5 and ch <= th + 0.5 and tw <= pw and th <= ph:
        cx, cy = (content[0] + content[2]) / 2, (content[1] + content[3]) / 2
        x0 = min(max(cx - tw / 2, page[0]), page[2] - tw)
        y0 = min(max(cy - th / 2, page[1]), page[3] - th)
        cand = (x0, y0, x0 + tw, y0 + th)
        if _contains(cand, content) and not any(_intersects(cand, o) for o in others):
            return cand
    pad = config.CROP_PADDING_PT
    return (max(page[0], content[0] - pad), max(page[1], content[1] - pad),
            min(page[2], content[2] + pad), min(page[3], content[3] + pad))


def _reading_order(boxes: list[Box]) -> list[Box]:
    """Top-to-bottom rows, left-to-right inside a row."""
    ordered = sorted(boxes, key=lambda b: (b[1] + b[3]) / 2)
    rows: list[list[Box]] = []
    for b in ordered:
        cy, h = (b[1] + b[3]) / 2, b[3] - b[1]
        if rows:
            ref = rows[-1][0]
            if abs(cy - (ref[1] + ref[3]) / 2) < 0.35 * min(h, ref[3] - ref[1]):
                rows[-1].append(b)
                continue
        rows.append([b])
    return [b for row in rows for b in sorted(row, key=lambda x: x[0])]


@dataclass
class Detection:
    cells: list[Box]       # crop rectangles; empty = use the whole page
    reliable: bool = True
    reason: str = ""


def detect_cells(page, words=None) -> Detection:
    """Find individual label rectangles on a page larger than one label."""
    els = collect_elements(page, words)
    if not els:
        return Detection([])
    pr = page.rect
    page_box: Box = (float(pr.x0), float(pr.y0), float(pr.x1), float(pr.y1))
    leaves = _cut(els)
    label_area = config.LABEL_W * config.LABEL_H
    if len(leaves) == 1:
        content = _union(leaves[0])
        w, h = _size(content)
        tol = config.SNAP_FIT_TOLERANCE_PT
        fits = (w <= config.LABEL_W + tol and h <= config.LABEL_H + tol) or \
               (w <= config.LABEL_H + tol and h <= config.LABEL_W + tol)
        if fits and _label_like(leaves[0]):
            return Detection([_snap(content, page_box, [])])
        return Detection([])
    contents = [_union(leaf) for leaf in leaves]
    for number, box in enumerate(contents, start=1):
        w, h = _size(box)
        if w * h > config.LABEL_OVERSIZE_FACTOR * label_area:
            return Detection([], False, f"region {number} is larger than one label")
    crops = [_snap(c, page_box, [o for j, o in enumerate(contents) if j != i])
             for i, c in enumerate(contents)]
    for i in range(len(crops)):
        for j in range(i + 1, len(crops)):
            if _intersects(crops[i], crops[j]):
                return Detection([], False, "label regions overlap")
    return Detection(_reading_order(crops))
