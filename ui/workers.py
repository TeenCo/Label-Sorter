"""Background work. The engine (``core``) knows nothing about Qt: it talks to the UI through
``AnalysisHooks``. ``QtHooks`` turns those callbacks into Qt signals, and turns the blocking
``ask_platform`` call into "pause the analysis, show the question, wait for the answer"."""
from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

from core import config, pdf_processor
from core.classifier import OcrEngine
from core.models import AnalysisResult, AskContext, Box, LabelInfo, PageInfo, Status
from core.pdf_analyzer import AnalysisCancelled, AnalysisHooks, analyze
from core.rendering import render_open_page, render_page_png

log = logging.getLogger(__name__)


@dataclass
class PreviewFrame:
    png: bytes
    caption: str
    source: Optional[tuple] = None   # (path, page, rect): lets the UI re-render (full page) while paused


@dataclass
class LabelEvent:
    filename: str
    page_number: int
    label_number: int
    label_total: int
    platform_key: str    # EBAY / TIKTOK / INPOST / SKIPPED / PENDING
    platform_name: str
    method: str
    note: str


class AnalysisSignals(QObject):
    progress = Signal(object)        # core.models.Progress
    log = Signal(str)
    preview = Signal(object)         # PreviewFrame (live)
    label = Signal(object)           # LabelEvent
    ask = Signal(object, object)     # AskContext, PreviewFrame
    finished = Signal(object)        # AnalysisResult
    cancelled = Signal()
    failed = Signal(str)


class GenerationSignals(QObject):
    progress = Signal(object)
    finished = Signal(object)        # pdf_processor.GenerationResult
    failed = Signal(str)


def _caption(path: Path, page_number: int, rect: Optional[Box], label_number: int = 0, label_total: int = 1) -> str:
    where = f"{Path(path).name} · page {page_number}"
    return where + (f" · label {label_number} of {label_total}" if label_total > 1 else "")


def _render(path: Path, page_number: int, rect: Optional[Box], max_side: int, page=None,
            fmt: str = "png") -> bytes:
    """Render from the already-open page when we have it; otherwise reopen the file."""
    try:
        if page is not None:
            return render_open_page(page, rect, max_side, fmt)
        return render_page_png(path, page_number, rect, max_side)
    except Exception as exc:  # noqa: BLE001
        log.warning("Preview failed for %s page %s: %s", path, page_number, exc)
        return b""


class QtHooks(AnalysisHooks):
    """Runs in the worker thread. Never touches widgets: it only emits signals."""

    def __init__(self, signals: AnalysisSignals, cancel_event: threading.Event) -> None:
        self.signals = signals
        self.cancel_event = cancel_event
        self._answers: queue.Queue = queue.Queue()
        self._last_live = 0.0
        self._last_progress = 0.0
        self.live_previews = True          # the UI turns this off while the window is minimised
        self._pending_frame: Optional[PreviewFrame] = None

    # -- engine -> UI
    def progress(self, p) -> None:
        now = time.monotonic()            # ~25 updates a second is plenty; always send the last one
        if p.done >= p.total or now - self._last_progress >= 0.04:
            self._last_progress = now
            self.signals.progress.emit(p)

    def log(self, message: str, level: str = "info") -> None:
        self.signals.log.emit(message)

    def page_started(self, path: Path, page_number: int, page=None) -> None:
        if not self.live_previews:
            return
        now = time.monotonic()
        if now - self._last_live < config.LIVE_PREVIEW_MIN_INTERVAL_S:
            return
        self._last_live = now
        jpg = _render(path, page_number, None, config.LIVE_PREVIEW_MAX_SIDE_PX, page, "jpeg")
        self.signals.preview.emit(PreviewFrame(jpg, _caption(path, page_number, None)))

    def show_preview(self, path: Path, page_number: int, rect: Optional[Box], page=None) -> None:
        """Called right before a question: render the exact label region in higher quality."""
        png = _render(path, page_number, rect, config.PREVIEW_MAX_SIDE_PX, page, "png")
        self._pending_frame = PreviewFrame(png, _caption(path, page_number, rect), (path, page_number, rect))

    def label_done(self, page: PageInfo, label: LabelInfo) -> None:
        if label.status is Status.CLASSIFIED and label.platform is not None:
            key, name = label.platform.key, label.platform.value
            note = label.evidence if label.method != "manual" else "chosen by you"
        elif label.status is Status.SKIPPED:
            key, name, note = "SKIPPED", "Skipped", "skipped by you"
        else:
            key, name, note = "PENDING", "Needs decision", label.detail or "decide later in Results"
        self.signals.label.emit(LabelEvent(page.filename, page.page_number, label.index + 1, len(page.labels),
                                           key, name, label.method, note))

    def ask_platform(self, ctx: AskContext) -> Optional[str]:
        """Pause the analysis until the UI answers. Returns a code, or None to decide later."""
        while True:                                   # drop answers left over from an earlier question
            try:
                self._answers.get_nowait()
            except queue.Empty:
                break
        frame = self._pending_frame or PreviewFrame(b"", f"{ctx.filename} · page {ctx.page_number}")
        self.signals.ask.emit(ctx, frame)
        while True:
            if self.cancel_event.is_set():
                return None
            try:
                return self._answers.get(timeout=0.1)
            except queue.Empty:
                continue

    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    # -- UI -> engine (called from the UI thread)
    def answer(self, code: Optional[str]) -> None:
        self._answers.put(code)


class AnalysisWorker(QThread):
    def __init__(self, files: list[Path], hooks: QtHooks, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.files = files
        self.hooks = hooks

    def run(self) -> None:
        signals = self.hooks.signals
        try:
            # OCR is probed lazily, the first time a label really needs it (the probe starts a
            # Tesseract process, which used to delay the first page on every run).
            result = analyze(self.files, self.hooks, OcrEngine())
            signals.finished.emit(result)
        except AnalysisCancelled:
            signals.cancelled.emit()
        except Exception:  # noqa: BLE001
            log.exception("Analysis failed")
            signals.failed.emit(traceback.format_exc())


class GenerationWorker(QThread):
    def __init__(self, result: AnalysisResult, out_dir: Path, signals: GenerationSignals,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.result, self.out_dir, self.signals = result, out_dir, signals

    def run(self) -> None:
        try:
            gen = pdf_processor.generate_outputs(self.result, self.out_dir, self.signals.progress.emit)
            self.signals.finished.emit(gen)
        except Exception:  # noqa: BLE001
            log.exception("Generation failed")
            self.signals.failed.emit(traceback.format_exc())
