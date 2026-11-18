"""Platform classification: native text first, OCR only as a fallback."""
from __future__ import annotations

import io
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core import config
from core.models import Box, Platform
from core.platforms import count_hits

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Classification:
    platform: Optional[Platform]
    method: str = ""          # "text" or "ocr"
    ambiguous: bool = False
    evidence: str = ""
    candidates: tuple[Platform, ...] = ()   # platforms named in the text (several = ambiguous)


def classify_text(text: str, method: str = "text") -> Classification:
    """Classify a block of text. Never guesses: no hit or a conflict returns no platform."""
    hits = {platform: n for platform, n in count_hits(text).items() if n}
    found = tuple(hits)
    if len(found) > 1:
        names = [p.value for p in found]
        said = f"both {names[0]} and {names[1]}" if len(names) == 2 else ", ".join(names)
        return Classification(None, method, True, f"text mentions {said}", found)
    if found:
        platform = found[0]
        return Classification(platform, method, False, f"found '{platform.value}' ({hits[platform]}x)", found)
    return Classification(None, method, False, "no platform name found")


class OcrEngine:
    """Lazy wrapper around Tesseract. Safe to construct when Tesseract is missing."""

    def __init__(self) -> None:
        self._checked = False
        self._available = False
        self.problem = ""

    @property
    def available(self) -> bool:
        if not self._checked:
            self._checked = True
            self._available = self._probe()
        return self._available

    def _probe(self) -> bool:
        try:
            import pytesseract
            from PIL import Image  # noqa: F401
        except ImportError as exc:
            self.problem = f"pytesseract/Pillow not installed ({exc})"
            return False
        cmd = shutil.which("tesseract")
        if not cmd:
            for candidate in config.TESSERACT_CANDIDATES:
                if candidate and Path(candidate).is_file():
                    cmd = candidate
                    break
        if not cmd:
            self.problem = "Tesseract executable not found"
            return False
        pytesseract.pytesseract.tesseract_cmd = cmd
        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:  # noqa: BLE001
            self.problem = f"Tesseract could not be started ({exc})"
            return False
        return True

    def read(self, page, clip: Optional[Box] = None) -> str:
        """OCR a page (or a clipped region). Rendering is for reading only; output PDFs never use it."""
        if not self.available:
            return ""
        import fitz
        import pytesseract
        from PIL import Image

        zoom = config.OCR_DPI / 72.0
        kwargs = {"matrix": fitz.Matrix(zoom, zoom), "alpha": False}
        if clip is not None:
            kwargs["clip"] = fitz.Rect(*clip)
        pix = page.get_pixmap(**kwargs)
        try:
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            return pytesseract.image_to_string(
                image, lang=config.OCR_LANG, config=f"--psm {config.OCR_PSM}",
                timeout=config.OCR_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001
            log.warning("OCR failed: %s", exc)
            return ""
        finally:
            pix = None
