"""Page rendering for on-screen previews (never used for the output PDFs)."""
from __future__ import annotations

from typing import Optional

from core import config
from core.models import Box


def render_page_png(path, page_number: int, clip: Optional[Box] = None,
                    max_side_px: int = config.PREVIEW_MAX_SIDE_PX) -> bytes:
    """Render one page (or a region) to PNG bytes for ON-SCREEN preview only."""
    import fitz

    doc = fitz.open(str(path))
    try:
        page = doc.load_page(page_number - 1)
        rect = fitz.Rect(*clip) if clip else page.rect
        zoom = min(max_side_px / max(rect.width, rect.height, 1.0), 3.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def excerpt(text: str, limit: int = 240) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "..."
