"""Central configuration: thresholds, platform patterns, paths and OCR settings.

Every tunable number used by the detection logic lives here so it can be
adjusted without touching the algorithms.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP_NAME = "Shipping Label Sorter"
APP_VERSION = "2.0.0"

# --------------------------------------------------------------------------
# Page geometry (PDF points; 72 points = 1 inch)
# --------------------------------------------------------------------------
PT_PER_INCH = 72.0
LABEL_W = 4 * PT_PER_INCH          # 288 pt  (4 in)
LABEL_H = 6 * PT_PER_INCH          # 432 pt  (6 in)
A4_SHORT = 595.276
A4_LONG = 841.89
SIZE_TOLERANCE_PT = 6.0            # ~0.08 in tolerance when comparing page sizes

# --------------------------------------------------------------------------
# Multi-label detection
# --------------------------------------------------------------------------
MULTI_LABEL_MIN_AREA_FACTOR = 1.6  # pages smaller than this x one label are never split
MIN_GAP_PT = 8.0                   # whitespace gap that may separate two labels
LABEL_MIN_SHORT_PT = 190.0         # a label's content must be at least this wide ...
LABEL_MIN_LONG_PT = 290.0          # ... and at least this tall (or the reverse)
LABEL_MIN_WORDS = 8                # words (or one image) needed to call a region a label
LABEL_OVERSIZE_FACTOR = 1.7        # a separated region larger than this x label is suspicious
NOISE_MAX_WORDS = 12               # footer/header scraps that may be ignored when splitting
NOISE_MAX_AREA_FACTOR = 0.12
CROP_PADDING_PT = 4.0
SNAP_FIT_TOLERANCE_PT = 12.0       # content this close to 4x6 is snapped to exactly 4x6
SEPARATOR_MAX_THICKNESS_PT = 2.0   # thin full-width lines (cut lines) are ignored
SEPARATOR_MIN_SPAN_FRACTION = 0.6
BACKGROUND_COVER_FRACTION = 0.9    # drawings covering this much of the page are backgrounds

# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------
# Platform name patterns live in core/platforms/<platform>.py
MIN_TEXT_CHARS_FOR_NATIVE = 15     # fewer characters than this = probably a scanned page

# --------------------------------------------------------------------------
# OCR (fallback only)
# --------------------------------------------------------------------------
OCR_DPI = 200
OCR_LANG = "eng"
OCR_PSM = 11                       # sparse text: good for logos scattered on a label
OCR_TIMEOUT_S = 45
TESSERACT_CANDIDATES = [
    os.environ.get("TESSERACT_CMD", ""),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    str(Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe"),
]

# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
PREVIEW_MAX_SIDE_PX = 900
LIVE_PREVIEW_MAX_SIDE_PX = 640     # preview shown while analysis is running
LIVE_PREVIEW_MIN_INTERVAL_S = 0.12  # at most ~8 live previews per second
DISK_SPACE_SAFETY_BYTES = 50 * 1024 * 1024
VERIFY_SIZE_TOLERANCE_PT = 0.6


def log_directory() -> Path:
    """Folder for the log file (per-user, created on demand)."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    path = base / "ShippingLabelSorter"
    path.mkdir(parents=True, exist_ok=True)
    return path
