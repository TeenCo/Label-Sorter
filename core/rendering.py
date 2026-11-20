"""Page rendering for on-screen previews (never used for the output PDFs)."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from core import config
from core.models import Box


def render_open_page(page, clip: Optional[Box] = None, max_side_px: int = config.LIVE_PREVIEW_MAX_SIDE_PX,
                     fmt: str = "jpeg") -> bytes:
    """Render an already-open page. No file is reopened, and JPEG skips PNG's slow compression,
    which is what the live view needs (screen only)."""
    import fitz

    rect = fitz.Rect(*clip) if clip else page.rect
    zoom = min(max_side_px / max(rect.width, rect.height, 1.0), 3.0)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False)
    return pix.tobytes("jpeg", jpg_quality=82) if fmt == "jpeg" else pix.tobytes("png")


@lru_cache(maxsize=48)
def _render_cached(path: str, page_number: int, clip: Optional[Box], max_side_px: int) -> bytes:
    import fitz

    doc = fitz.open(path)            # opened per call and closed again: no file stays locked
    try:
        return render_open_page(doc.load_page(page_number - 1), clip, max_side_px, "png")
    finally:
        doc.close()


def render_page_png(path, page_number: int, clip: Optional[Box] = None,
                    max_side_px: int = config.PREVIEW_MAX_SIDE_PX) -> bytes:
    """Render one page (or a region) to PNG bytes for ON-SCREEN preview only.
    Recent previews are cached (bytes only), so flipping between rows is instant."""
    return _render_cached(str(path), int(page_number), tuple(clip) if clip else None, int(max_side_px))


def clear_preview_cache() -> None:
    _render_cached.cache_clear()


def excerpt(text: str, limit: int = 240) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "..."
