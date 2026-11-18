"""Scan the selected PDFs page by page and classify every label."""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

from core import config
from core.classifier import OcrEngine, classify_text
from core.label_detector import (SizeClass, classify_size, crop_is_safe, describe_size, detect_cells)
from core.models import (SKIP_CODE, AnalysisResult, AskContext, Box, FileInfo, FileIssue, Flag, FlagKind,
                         LabelInfo, PageInfo, Platform, Progress, Status)
from core.rendering import excerpt

log = logging.getLogger(__name__)


class AnalysisCancelled(Exception):
    """Raised when the user cancels analysis."""


class AnalysisHooks:
    """Callbacks used by the analyzer. Subclass to connect it to a GUI or a test."""

    def progress(self, p: Progress) -> None: ...

    def log(self, message: str, level: str = "info") -> None: ...

    def show_preview(self, path: Path, page_number: int, rect: Optional[Box]) -> None: ...

    def page_started(self, path: Path, page_number: int) -> None:
        """A page is about to be analysed (used for the live view)."""

    def label_done(self, page: PageInfo, label: LabelInfo) -> None:
        """A label has its final result for this run (classified, skipped or left unresolved)."""

    def ask_platform(self, ctx: AskContext) -> Optional[str]:
        """Block until the user decides. Return "E", "T", "I" (platform), "S" (skip) or None
        (leave unresolved for the review screen). Blocking here pauses the analysis."""
        return None

    def cancelled(self) -> bool:
        return False


def inspect_file(path: Path) -> tuple[int, str]:
    """Return (page_count, error). A non-empty error means the file cannot be processed."""
    import fitz

    try:
        if not path.is_file():
            return 0, "file not found or not accessible"
        if path.suffix.lower() != ".pdf":
            return 0, "not a PDF file"
        if path.stat().st_size == 0:
            return 0, "file is empty (0 bytes)"
        doc = fitz.open(str(path))
    except PermissionError:
        return 0, "access denied (file locked or no permission)"
    except Exception as exc:  # noqa: BLE001
        return 0, f"cannot be opened - corrupted or unreadable ({exc})"
    try:
        if doc.needs_pass:
            return 0, "password-protected"
        if doc.page_count == 0:
            return 0, "contains no pages"
        doc.load_page(0)
        return doc.page_count, ""
    except Exception as exc:  # noqa: BLE001
        return 0, f"corrupted or unreadable ({exc})"
    finally:
        doc.close()


def _words_text(words, box: Box) -> str:
    out = []
    for w in words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
            out.append(w[4])
    return " ".join(out)


def _fingerprint(text: str) -> str:
    norm = re.sub(r"[^a-z0-9]", "", text.lower())
    return hashlib.sha1(norm.encode()).hexdigest() if len(norm) >= 40 else ""


def _plan_cells(page, info: PageInfo) -> list[Optional[Box]]:
    """Decide how many labels a page holds. [None] means 'the whole page is one label'."""
    safe, why = crop_is_safe(page)
    if not safe:
        info.static_flags.append(Flag(
            FlagKind.MULTI_UNSPLIT,
            f"Page is larger than one label but cannot be analysed or cropped safely ({why}); kept whole", True))
        return [None]
    det = detect_cells(page)
    if not det.reliable:
        info.static_flags.append(Flag(
            FlagKind.MULTI_UNSPLIT,
            f"Possible multi-label page could not be separated reliably ({det.reason}); kept whole", True))
        return [None]
    if not det.cells:
        return [None]
    if len(det.cells) >= 2:
        info.static_flags.append(Flag(
            FlagKind.MULTI_LABEL, f"Page contains {len(det.cells)} labels; separated into individual pages", False))
    return list(det.cells)


def _analyze_page(doc, path: Path, file_index: int, page_index: int, ocr: OcrEngine,
                  hooks: AnalysisHooks, seen: dict[str, str]) -> PageInfo:
    hooks.page_started(path, page_index + 1)
    page = doc.load_page(page_index)
    w, h = float(page.rect.width), float(page.rect.height)
    size_class = classify_size(w, h)
    info = PageInfo(file_index=file_index, path=path, page_number=page_index + 1, width=w, height=h,
                    rotation=int(page.rotation), size_class=size_class.value)

    cells: list[Optional[Box]] = [None]
    if size_class is not SizeClass.LABEL_4X6:
        info.static_flags.append(Flag(FlagKind.NON_STANDARD_SIZE, describe_size(w, h, size_class), False))
        if w * h >= config.MULTI_LABEL_MIN_AREA_FACTOR * config.LABEL_W * config.LABEL_H:
            cells = _plan_cells(page, info)

    page_text = page.get_text("text") if None in cells else ""
    words = page.get_text("words") if any(c is not None for c in cells) else []

    for index, cell in enumerate(cells):
        size = (w, h) if cell is None else (cell[2] - cell[0], cell[3] - cell[1])
        label = LabelInfo(index=index, rect=cell, out_size=size)
        text = page_text if cell is None else _words_text(words, cell)
        cls = classify_text(text)
        if cls.platform is None and not cls.ambiguous and ocr.available:
            cls = classify_text(ocr.read(page, cell), method="ocr")
        if cls.platform is not None:
            label.set_platform(cls.platform, cls.method, cls.evidence)
        else:
            label.detail = cls.evidence
            if not ocr.available and len(text.strip()) < config.MIN_TEXT_CHARS_FOR_NATIVE:
                label.detail += f" (page has little text and OCR is unavailable: {ocr.problem})"
        fp = _fingerprint(text)
        if fp:
            if fp in seen:
                label.duplicate_of = seen[fp]
            else:
                seen[fp] = f"{path.name} page {page_index + 1}"
        info.labels.append(label)
        if label.status is Status.UNRECOGNIZED:
            _ask_user(info, label, text, hooks, cls)
        hooks.label_done(info, label)
    return info


def _ask_user(info: PageInfo, label: LabelInfo, text: str, hooks: AnalysisHooks, cls) -> None:
    hooks.show_preview(info.path, info.page_number, label.rect)
    ctx = AskContext(filename=info.filename, page_number=info.page_number,
                     label_number=label.index + 1, label_total=len(info.labels),
                     reason=label.detail or "platform not recognized", excerpt=excerpt(text),
                     ambiguous=cls.ambiguous, candidates=cls.candidates)
    choice = hooks.ask_platform(ctx)
    platform = Platform.from_code(choice)
    if platform is not None:
        label.set_platform(platform, "manual")
    elif str(choice or "").strip().upper() == SKIP_CODE:
        label.skip()
    # None: stays UNRECOGNIZED and must be settled on the review screen


def _error_page(doc, path: Path, file_index: int, page_index: int, exc: Exception) -> PageInfo:
    w = h = 0.0
    rotation = 0
    try:
        page = doc.load_page(page_index)
        w, h, rotation = float(page.rect.width), float(page.rect.height), int(page.rotation)
    except Exception:  # noqa: BLE001
        pass
    label = LabelInfo(index=0, rect=None, out_size=(w, h), detail=f"page could not be analysed ({exc})")
    info = PageInfo(file_index=file_index, path=path, page_number=page_index + 1, width=w, height=h,
                    rotation=rotation, size_class=classify_size(w, h).value, labels=[label])
    info.static_flags.append(Flag(FlagKind.ANALYSIS_ERROR, f"Analysis failed: {exc}", True))
    return info


def analyze(paths: list[Path], hooks: Optional[AnalysisHooks] = None,
            ocr: Optional[OcrEngine] = None) -> AnalysisResult:
    """Analyze files in the given order. A bad file is reported and skipped, never fatal."""
    import fitz

    hooks = hooks or AnalysisHooks()
    ocr = ocr or OcrEngine()
    result = AnalysisResult(inputs=[Path(p) for p in paths])

    for path in result.inputs:
        count, error = inspect_file(path)
        if error:
            result.issues.append(FileIssue(path, error))
            result.files.append(FileInfo(path, 0, False))
            hooks.log(f"{path.name}: {error} - file skipped", "error")
            log.error("%s: %s", path, error)
        else:
            result.files.append(FileInfo(path, count, True))

    total = sum(f.page_count for f in result.good_files)
    file_total = len(result.good_files)
    done = file_no = 0
    seen: dict[str, str] = {}

    for file_index, finfo in enumerate(result.files):
        if not finfo.ok:
            continue
        file_no += 1
        try:
            doc = fitz.open(str(finfo.path))
        except Exception as exc:  # noqa: BLE001
            finfo.ok = False
            result.issues.append(FileIssue(finfo.path, f"cannot be opened ({exc})"))
            hooks.log(f"{finfo.path.name}: cannot be opened - file skipped", "error")
            continue
        pages: list[PageInfo] = []
        try:
            for page_index in range(finfo.page_count):
                if hooks.cancelled():
                    raise AnalysisCancelled()
                try:
                    pages.append(_analyze_page(doc, finfo.path, file_index, page_index, ocr, hooks, seen))
                except AnalysisCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001
                    log.exception("Page analysis failed: %s page %d", finfo.path, page_index + 1)
                    hooks.log(f"{finfo.path.name} page {page_index + 1}: analysis error: {exc}", "error")
                    pages.append(_error_page(doc, finfo.path, file_index, page_index, exc))
                done += 1
                hooks.progress(Progress("Analyzing", finfo.path.name, file_no, file_total,
                                        page_index + 1, finfo.page_count, done, total))
        finally:
            doc.close()
        result.pages.extend(pages)
    result.assign_prints_pages()
    return result
