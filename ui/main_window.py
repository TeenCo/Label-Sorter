"""Main window: sidebar + one page per step. Owns the batch state and the background workers."""
from __future__ import annotations

import logging
import sys
import threading
from typing import Optional

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from core import config, file_manager
from core.models import AnalysisResult
from core.pdf_processor import GenerationResult
from ui.dialogs import DeleteDialog, notice
from ui.pages.analysis_page import AnalysisPage
from ui.pages.exceptions_page import ExceptionsPage
from ui.pages.files_page import FilesPage
from ui.pages.output_page import OutputPage
from ui.pages.results_page import ResultsPage
from ui.sidebar import Sidebar
from ui.widgets import Toast, adapt_split, crossfade, fade_in
from ui.workers import AnalysisSignals, AnalysisWorker, GenerationSignals, GenerationWorker, QtHooks

log = logging.getLogger(__name__)

FILES, ANALYSIS, RESULTS, EXCEPTIONS, OUTPUT = range(5)

COMPACT_BELOW = 1000        # window width (px) under which the sidebar becomes an icon rail
NARROW_BELOW = 980          # ... and pages stack their preview under the content
MAX_CONTENT_WIDTH = 1500    # on fullscreen / ultrawide screens the content stays centred


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        icon = config.resource_path("assets", "app.ico")
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.setMinimumSize(760, 520)                 # small ("cropped") windows stay usable
        self.resize(1320, 840)
        self._settings = QSettings("ShippingLabelSorter", "ShippingLabelSorter")
        self._narrow: Optional[bool] = None
        self._deferred_built = False

        # ---- batch state
        self.result: Optional[AnalysisResult] = None
        self.gen: Optional[GenerationResult] = None
        self.unlocked: set[int] = {FILES}
        self.done: set[int] = set()
        self.cancel_event = threading.Event()
        self.hooks: Optional[QtHooks] = None
        self.analysis_worker: Optional[AnalysisWorker] = None
        self.gen_worker: Optional[GenerationWorker] = None
        self._dark_title_done = False

        # ---- layout
        root = QWidget()
        root.setObjectName("Root")
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.sidebar = Sidebar()
        row.addWidget(self.sidebar)
        row.addStretch(1)                              # content is centred when the window is very wide
        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")
        self.stack.setMaximumWidth(MAX_CONTENT_WIDTH)
        row.addWidget(self.stack, 1000)                # ~1 px of slack at normal sizes, centred when capped
        row.addStretch(1)
        self.setCentralWidget(root)

        # Only the first two pages are built before the window appears; the rest are built right
        # after the first paint (or earlier if needed), which gets the window on screen sooner.
        self.files_page = FilesPage()
        self.analysis_page = AnalysisPage()
        self.stack.addWidget(self.files_page)
        self.stack.addWidget(self.analysis_page)
        for _ in (RESULTS, EXCEPTIONS, OUTPUT):
            self.stack.addWidget(QWidget())            # placeholders keep the step indexes stable
        self.toast = Toast(root)

        # ---- wiring
        self.sidebar.step_clicked.connect(self._on_step)
        self.files_page.start_requested.connect(self.start_analysis)
        self.files_page.message.connect(self.toast.show_message)
        self.analysis_page.decided.connect(self._relay_answer)
        self.analysis_page.cancel_requested.connect(self._cancel_analysis)

        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._browse_shortcut)
        QShortcut(QKeySequence("F11"), self, activated=self._toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, activated=self._leave_fullscreen)
        self._go(FILES, animate=False)
        self._restore_window()
        self._apply_layout_mode(force=True)
        QTimer.singleShot(0, self._build_deferred_pages)

    def _build_deferred_pages(self) -> None:
        """Results, Exceptions and Output are needed only after an analysis."""
        if self._deferred_built:
            return
        self._deferred_built = True
        self.results_page = ResultsPage()
        self.exceptions_page = ExceptionsPage()
        self.output_page = OutputPage()
        for index, page in ((RESULTS, self.results_page), (EXCEPTIONS, self.exceptions_page),
                            (OUTPUT, self.output_page)):
            placeholder = self.stack.widget(index)
            current = self.stack.currentIndex()
            self.stack.removeWidget(placeholder)
            placeholder.deleteLater()
            self.stack.insertWidget(index, page)
            self.stack.setCurrentIndex(current)
        self.results_page.continue_requested.connect(lambda: self._go(EXCEPTIONS))
        self.results_page.changed.connect(self._results_changed)
        self.results_page.message.connect(self.toast.show_message)
        self.exceptions_page.back_requested.connect(lambda: self._go(RESULTS))
        self.exceptions_page.resolve_requested.connect(self._show_pending)
        self.exceptions_page.generate_requested.connect(self.generate)
        self.exceptions_page.message.connect(self.toast.show_message)
        self.output_page.delete_requested.connect(self._delete_originals)
        self.output_page.new_batch_requested.connect(self._new_batch)
        self.output_page.back_requested.connect(lambda: self._go(EXCEPTIONS))
        self._apply_layout_mode(force=True)

    # ------------------------------------------------------------ navigation
    def _states(self) -> list[str]:
        current = self.stack.currentIndex()
        out = []
        for i in range(5):
            if i == current:
                out.append("active")
            elif i in self.done:
                out.append("done")
            elif i in self.unlocked:
                out.append("todo")
            else:
                out.append("locked")
        return out

    def _go(self, index: int, animate: bool = True) -> None:
        if index == EXCEPTIONS and self.result is not None:
            self.exceptions_page.load(self.result)
        self.unlocked.add(index)
        old = self.stack.currentWidget()
        snapshot = old.grab() if (animate and self.isVisible() and not self.isMinimized()) else None
        self.stack.setCurrentIndex(index)
        new = self.stack.currentWidget()
        if snapshot is not None and old is not new:
            crossfade(self.stack, snapshot, new)
        self.sidebar.set_states(self._states())

    def _on_step(self, index: int) -> None:
        if self._generating():
            self.toast.show_message("Please wait until the PDFs are generated")
            return
        if self._analyzing() and index != ANALYSIS:
            self.toast.show_message("Cancel the analysis first to leave this screen")
            return
        if index in self.unlocked:
            self._go(index)

    def _analyzing(self) -> bool:
        return self.analysis_worker is not None and self.analysis_worker.isRunning()

    def _generating(self) -> bool:
        return self.gen_worker is not None and self.gen_worker.isRunning()

    def _browse_shortcut(self) -> None:
        if self.stack.currentIndex() == FILES:
            self.files_page.browse()

    # ------------------------------------------------------------ analysis
    def start_analysis(self) -> None:
        files = self.files_page.files()
        if not files or self._analyzing():
            return
        self._build_deferred_pages()
        self.result, self.gen = None, None
        self.done = {FILES}
        self.unlocked = {FILES, ANALYSIS}
        self.sidebar.hide_summary()
        self.analysis_page.begin()
        self.cancel_event.clear()

        signals = AnalysisSignals(self)
        signals.progress.connect(self.analysis_page.on_progress)
        signals.log.connect(self.analysis_page.set_log)
        signals.preview.connect(self.analysis_page.on_preview)
        signals.label.connect(self.analysis_page.on_label)
        signals.ask.connect(self._on_ask)
        signals.finished.connect(self._analysis_done)
        signals.cancelled.connect(self._analysis_cancelled)
        signals.failed.connect(self._analysis_failed)
        self.hooks = QtHooks(signals, self.cancel_event)
        self.analysis_worker = AnalysisWorker(files, self.hooks, self)
        self.analysis_worker.finished.connect(self._worker_finished)
        self.analysis_worker.start()
        self._go(ANALYSIS)

    def _on_ask(self, ctx, frame) -> None:
        self.analysis_page.on_ask(ctx, frame)
        _alert(self)

    def _relay_answer(self, code) -> None:
        if self.hooks is not None:
            self.hooks.answer(code)

    def _cancel_analysis(self) -> None:
        self.cancel_event.set()
        self.analysis_page.cancel_btn.setEnabled(False)
        self.analysis_page.cancel_btn.setText("Cancelling…")

    def _worker_finished(self) -> None:
        worker, self.analysis_worker = self.analysis_worker, None
        if worker is not None:
            worker.deleteLater()
        self.analysis_page.cancel_btn.setText("Cancel analysis")

    def _analysis_done(self, result: AnalysisResult) -> None:
        self.result = result
        if result.issues:
            text = "\n".join(f"{i.path.name}: {i.reason}" for i in result.issues)
            notice(self, "Some files were skipped",
                   "These files could not be processed and were left untouched:\n\n" + text, "warn")
        if not result.pages:
            notice(self, "Nothing to analyze", "None of the selected files could be read.", "error")
            self._go(FILES)
            return
        self.analysis_page.finish()
        self.results_page.load(result)
        self.done.add(ANALYSIS)
        self.unlocked |= {RESULTS, EXCEPTIONS}
        self._update_summary()
        self._go(RESULTS)

    def _analysis_cancelled(self) -> None:
        self.toast.show_message("Analysis cancelled. Nothing was changed.")
        self.unlocked = {FILES}
        self.done = set()
        self._go(FILES)

    def _analysis_failed(self, trace: str) -> None:
        log.error(trace)
        notice(self, "Something went wrong", "An unexpected error occurred. No files were changed.\n\n"
               + trace[-1200:], "error")
        self.unlocked = {FILES}
        self.done = set()
        self._go(FILES)

    # ------------------------------------------------------------ results
    def _results_changed(self) -> None:
        self._update_summary()

    def _update_summary(self) -> None:
        if self.result is None:
            return
        s = self.result.stats()
        self.sidebar.set_summary(s.ebay_labels, s.tiktok_labels, s.inpost_labels, len(self.result.pending_labels()))

    def _show_pending(self) -> None:
        self._go(RESULTS)
        self.results_page.show_pending()

    # ------------------------------------------------------------ generation
    def generate(self) -> None:
        if self.result is None or self._generating():
            return
        if self.result.pending_labels():
            self.toast.show_message("Some labels still need a decision")
            self._show_pending()
            return
        out_dir = self.files_page.out_dir()
        if out_dir is None:
            return
        self.done |= {RESULTS}
        self.output_page.begin()
        self._go(OUTPUT)
        signals = GenerationSignals(self)
        signals.progress.connect(self.output_page.on_progress)
        signals.finished.connect(self._generation_done)
        signals.failed.connect(self._generation_failed)
        self.gen_worker = GenerationWorker(self.result, out_dir, signals, self)
        self.gen_worker.finished.connect(self._gen_worker_finished)
        self.gen_worker.start()

    def _gen_worker_finished(self) -> None:
        worker, self.gen_worker = self.gen_worker, None
        if worker is not None:
            worker.deleteLater()

    def _generation_done(self, gen: GenerationResult) -> None:
        self.gen = gen
        if not gen.ok:
            self.output_page.show_failure(gen)
            self.sidebar.set_states(self._states())
            return
        assert self.result is not None
        self.done |= {EXCEPTIONS, OUTPUT}
        self.output_page.show_success(self.result, gen)
        self.sidebar.set_states(self._states())

    def _generation_failed(self, trace: str) -> None:
        log.error(trace)
        failed = GenerationResult(errors=["An unexpected error occurred. No files were changed.", trace[-800:]])
        self.output_page.show_failure(failed)

    # ------------------------------------------------------------ originals
    def _confirm_delete(self, files) -> bool:
        return bool(DeleteDialog(self, list(files)).exec())

    def _delete_originals(self) -> None:
        if self.result is None or self.gen is None:
            return
        candidates = [f.path for f in self.result.good_files]
        res = file_manager.request_deletion(candidates, self.gen.verified, self._confirm_delete,
                                            self.gen.outputs.values())
        text = res.message
        if res.failed:
            text += "\n" + "\n".join(f"Could not delete {p.name}: {err}" for p, err in res.failed)
        if self.result.issues:
            text += "\nFiles that failed to process were never offered for deletion."
        self.output_page.set_delete_result(text, remove_button=res.confirmed)
        if res.deleted:
            self.toast.show_message(f"Deleted {len(res.deleted)} original file{'s' if len(res.deleted) != 1 else ''}")

    def _new_batch(self) -> None:
        self.result, self.gen = None, None
        self.files_page.clear()
        self.unlocked, self.done = {FILES}, set()
        self.sidebar.hide_summary()
        self._go(FILES)

    # ------------------------------------------------------------ window
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if sys.platform.startswith("win") and not self._dark_title_done:
            self._dark_title_done = True
            try:                                    # dark title bar on Windows 10/11
                import ctypes
                value = ctypes.c_int(1)
                hwnd = int(self.winId())
                for attribute in (20, 19):
                    if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                                  ctypes.sizeof(value)) == 0:
                        break
            except Exception:  # noqa: BLE001
                pass

    def _apply_layout_mode(self, force: bool = False) -> None:
        """Responsive rules: icon-only sidebar and stacked previews on narrow windows."""
        width = self.width()
        self.sidebar.set_compact(width < COMPACT_BELOW, animate=not force)
        narrow = width < NARROW_BELOW
        if narrow == self._narrow and not force:
            return
        self._narrow = narrow
        pages = [self.analysis_page]
        if self._deferred_built:
            pages += [self.results_page, self.exceptions_page]
        for page in pages:
            adapt_split(page.split_root, page.preview, narrow, page.preview_width)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self._leave_fullscreen()
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()

    def _leave_fullscreen(self) -> None:
        if self.isFullScreen():
            if getattr(self, "_was_maximized", False):
                self.showMaximized()
            else:
                self.showNormal()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        hooks = getattr(self, "hooks", None)
        if event.type() == QEvent.Type.WindowStateChange and hooks is not None:
            # nothing to draw while minimised: skip live previews (analysis itself keeps running)
            hooks.live_previews = not self.isMinimized()

    def _restore_window(self) -> None:
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            self._apply_layout_mode()
        if self.toast.isVisible():
            self.toast.move((self.centralWidget().width() - self.toast.width()) // 2,
                            self.centralWidget().height() - self.toast.height() - 28)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._generating():
            self.toast.show_message("Please wait until the PDFs are generated")
            event.ignore()
            return
        worker = self.analysis_worker
        if worker is not None and worker.isRunning():
            self.cancel_event.set()
            worker.wait(4000)
        if not self.isFullScreen() and not self.isMinimized():
            self._settings.setValue("geometry", self.saveGeometry())
        event.accept()


def _alert(window: QWidget) -> None:
    """Flash the taskbar entry when the analysis needs the user while the window is in the background."""
    if not window.isActiveWindow():
        QApplication.alert(window, 0)
