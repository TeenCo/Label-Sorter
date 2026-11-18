"""Verification of generated PDFs (reopen + structure check)."""
from __future__ import annotations

import logging
from pathlib import Path

from core import config

log = logging.getLogger(__name__)


def verify_pdf(path: Path, expected_sizes: list[tuple[float, float]]) -> list[str]:
    """Reopen ``path`` with PyMuPDF and pypdf; return a list of problems (empty = OK)."""
    import fitz

    problems: list[str] = []
    if not Path(path).is_file():
        return [f"{Path(path).name}: file does not exist"]
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001
        return [f"{Path(path).name}: cannot be reopened ({exc})"]
    try:
        if doc.needs_pass:
            problems.append(f"{Path(path).name}: unexpectedly encrypted")
        if doc.page_count != len(expected_sizes):
            problems.append(f"{Path(path).name}: has {doc.page_count} pages, expected {len(expected_sizes)}")
        for i in range(min(doc.page_count, len(expected_sizes))):
            rect = doc.load_page(i).rect
            ew, eh = expected_sizes[i]
            if ew <= 0 or eh <= 0:
                continue
            tol = config.VERIFY_SIZE_TOLERANCE_PT
            if abs(rect.width - ew) > tol or abs(rect.height - eh) > tol:
                problems.append(f"{Path(path).name}: page {i + 1} is {rect.width:.1f}x{rect.height:.1f} pt, "
                                f"expected {ew:.1f}x{eh:.1f} pt")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"{Path(path).name}: error while checking pages ({exc})")
    finally:
        doc.close()
    # Independent second opinion from a different PDF parser.
    try:
        from pypdf import PdfReader
        count = len(PdfReader(str(path)).pages)
        if count != len(expected_sizes):
            problems.append(f"{Path(path).name}: pypdf counts {count} pages, expected {len(expected_sizes)}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"{Path(path).name}: pypdf could not read the file ({exc})")
    return problems
