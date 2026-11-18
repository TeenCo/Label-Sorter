"""Step 5: generating, the finished files, and the (optional) deletion of the originals."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QProgressBar, QStackedLayout, QVBoxLayout, QWidget

from core import file_manager, pdf_processor
from core.models import AnalysisResult, Progress
from ui import theme
from ui.widgets import Banner, Card, animate_progress, button, fade_in, label, set_state

KIND_TITLES = {"EBAY": "eBay labels", "TIKTOK": "TikTok labels", "INPOST": "InPost labels",
               "PRINTS": "PRINTS: every original page"}


class _Dot(QFrame):
    def __init__(self, key: str) -> None:
        super().__init__()
        self.setFixedSize(10, 10)
        self._color = QColor(theme.PALETTE.get(key, theme.PALETTE["faint"]))

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(0, 0, 10, 10)


class OutputPage(QWidget):
    new_batch_requested = Signal()
    back_requested = Signal()
    delete_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._folder = None
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 24)
        root.setSpacing(16)
        self.title = label("Generating PDFs", "Title")
        self.subtitle = label("", "Subtitle", wrap=True)
        root.addWidget(self.title)
        root.addWidget(self.subtitle)

        host = QWidget()
        self.stack = QStackedLayout(host)
        root.addWidget(host, 1)

        # ---- 0: working
        work = QWidget()
        wl = QVBoxLayout(work)
        wl.setContentsMargins(0, 0, 0, 0)
        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(8)
        self.work_detail = label("Starting…", "CardTitle")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.work_hint = label("Pages are copied without being re-rendered. Each output file is reopened and "
                               "checked before it is saved.", "Muted", wrap=True)
        for w in (self.work_detail, self.bar, self.work_hint):
            cl.addWidget(w)
        wl.addWidget(card)
        wl.addStretch(1)
        self.stack.addWidget(work)

        # ---- 1: done
        done = QWidget()
        dl = QVBoxLayout(done)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(14)
        self.verified = Banner("Every output file was reopened and verified.", "ok")
        dl.addWidget(self.verified)
        self.files_box = QVBoxLayout()
        self.files_box.setSpacing(10)
        dl.addLayout(self.files_box)
        self.reports = label("", "Faint", wrap=True)
        dl.addWidget(self.reports)

        self.orig_card = Card()
        ol = QVBoxLayout(self.orig_card)
        ol.setContentsMargins(20, 16, 20, 16)
        ol.setSpacing(8)
        ol.addWidget(label("Original files", "CardTitle"))
        self.orig_text = label("", "Muted", wrap=True)
        ol.addWidget(self.orig_text)
        row = QHBoxLayout()
        self.delete_btn = button("Delete original files…", "danger")
        self.delete_btn.clicked.connect(self.delete_requested.emit)
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        ol.addLayout(row)
        dl.addWidget(self.orig_card)
        dl.addStretch(1)

        bar_row = QHBoxLayout()
        self.new_btn = button("New batch", "ghost")
        self.new_btn.clicked.connect(self.new_batch_requested.emit)
        self.open_btn = button("Open output folder", "primary")
        self.open_btn.clicked.connect(self._open_folder)
        bar_row.addWidget(self.new_btn)
        bar_row.addStretch(1)
        bar_row.addWidget(self.open_btn)
        dl.addLayout(bar_row)
        self.stack.addWidget(done)

        # ---- 2: failed
        fail = QWidget()
        fl = QVBoxLayout(fail)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(14)
        self.fail_banner = Banner("", "danger")
        fl.addWidget(self.fail_banner)
        fl.addStretch(1)
        back_row = QHBoxLayout()
        self.back_btn = button("Back to review")
        self.back_btn.clicked.connect(self.back_requested.emit)
        back_row.addStretch(1)
        back_row.addWidget(self.back_btn)
        fl.addLayout(back_row)
        self.stack.addWidget(fail)

    # ------------------------------------------------------------ states
    def begin(self) -> None:
        self.title.setText("Generating PDFs")
        self.subtitle.setText("This usually takes a few seconds.")
        self.work_detail.setText("Starting…")
        self.bar.setValue(0)
        set_state(self.bar, "")
        self.stack.setCurrentIndex(0)

    def on_progress(self, p: Progress) -> None:
        self.work_detail.setText(f"{p.filename}  ·  page {p.page_no} of {p.page_total}")
        animate_progress(self.bar, int(100 * p.done / max(p.total, 1)))

    def show_success(self, result: AnalysisResult, gen: pdf_processor.GenerationResult) -> None:
        self.title.setText("Your files are ready")
        self.subtitle.setText("Nothing was changed or deleted yet. The originals are still where they were.")
        while self.files_box.count():
            item = self.files_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for kind in ("EBAY", "TIKTOK", "INPOST", "PRINTS"):
            path = gen.outputs.get(kind)
            if path is None:
                continue
            card = Card()
            lay = QHBoxLayout(card)
            lay.setContentsMargins(18, 12, 14, 12)
            lay.setSpacing(12)
            lay.addWidget(_Dot(kind))
            text = QVBoxLayout()
            text.setSpacing(0)
            text.addWidget(label(path.name, "CardTitle"))
            pages = gen.page_counts.get(kind, 0)
            text.addWidget(label(f"{KIND_TITLES[kind]}  ·  {pages} page{'s' if pages != 1 else ''}", "Muted"))
            lay.addLayout(text, 1)
            b = button("Show in folder", "ghost")
            b.clicked.connect(lambda _=False, f=path.parent: file_manager.open_folder(f))
            lay.addWidget(b)
            self.files_box.addWidget(card)
        names = [p.name for p in (gen.report_path, gen.csv_path) if p]
        self.reports.setText("Also saved: " + ", ".join(names) if names else "")
        s = result.stats()
        if s.review_pages:
            self.reports.setText(self.reports.text() + f"\n{s.review_pages} flagged page(s) are listed in the report.")
        if gen.errors:
            self.verified.text.setText("Finished with warnings: " + "; ".join(gen.errors))
            self.verified.set_kind("")
        else:
            self.verified.text.setText("Every output file was reopened and verified.")
            self.verified.set_kind("ok")
        self._folder = next(iter(gen.outputs.values())).parent
        count = len(result.good_files)
        self.orig_text.setText(f"The {count} original PDF{'s' if count != 1 else ''} can be deleted now that the "
                               "outputs are verified. Files that failed to process are never offered.")
        self.delete_btn.setVisible(True)
        self.delete_btn.setText(f"Delete {count} original file{'s' if count != 1 else ''}…")
        self.stack.setCurrentIndex(1)
        fade_in(self.stack.currentWidget())

    def show_failure(self, gen: pdf_processor.GenerationResult) -> None:
        self.title.setText("The PDFs could not be generated")
        self.subtitle.setText("No original file was touched and no partial output was kept.")
        self.fail_banner.text.setText("\n".join(gen.errors) or "Unknown error")
        self.stack.setCurrentIndex(2)

    def set_delete_result(self, text: str, remove_button: bool = False) -> None:
        self.orig_text.setText(text)
        if remove_button:
            self.delete_btn.setVisible(False)

    def _open_folder(self) -> None:
        if self._folder:
            file_manager.open_folder(self._folder)
