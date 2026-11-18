"""Step 4: flagged pages, then generate. Generating stays blocked while any label is undecided."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QStackedLayout, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import pdf_processor
from core.models import AnalysisResult
from ui import theme
from ui.widgets import PLATFORM_ROLE, Banner, Card, PlatformDelegate, PreviewPane, StatTile, button, label


class ExceptionsPage(QWidget):
    back_requested = Signal()
    resolve_requested = Signal()
    generate_requested = Signal()
    message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.result: Optional[AnalysisResult] = None
        self._row_pages: list[int] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 24)
        root.setSpacing(20)
        left = QVBoxLayout()
        left.setSpacing(14)
        root.addLayout(left, 1)

        left.addWidget(label("Check before you generate", "Title"))
        left.addWidget(label("Pages that need a second look. “PRINTS page” is the page number inside the "
                             "PRINTS PDF, so you can find it when printing.", "Subtitle", wrap=True))

        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tiles = {"PAGES": StatTile("Pages in PRINTS"), "EBAY": StatTile("eBay labels", "EBAY"),
                      "TIKTOK": StatTile("TikTok labels", "TIKTOK"), "INPOST": StatTile("InPost labels", "INPOST"),
                      "FLAGS": StatTile("Flagged pages", "warn")}
        for t in self.tiles.values():
            tiles.addWidget(t, 1)
        left.addLayout(tiles)

        self.banner = Banner("", "", "Resolve them")
        self.banner.action.clicked.connect(self.resolve_requested.emit)
        left.addWidget(self.banner)

        card = Card()
        stack_host = QVBoxLayout(card)
        stack_host.setContentsMargins(6, 6, 6, 6)
        holder = QWidget()
        self.stack = QStackedLayout(holder)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Status", "File", "Page", "PRINTS page", "Details"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setItemDelegateForColumn(0, PlatformDelegate(self.table))
        self.table.setWordWrap(True)
        head = self.table.horizontalHeader()
        for col, mode in enumerate((QHeaderView.ResizeMode.Fixed, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.Stretch)):
            head.setSectionResizeMode(col, mode)
        self.table.setColumnWidth(0, 140)
        self.empty = label("No flagged pages.\nEvery page was recognised cleanly.", "Muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        stack_host.addWidget(holder)
        left.addWidget(card, 1)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.back_btn = button("Back to results", "ghost")
        self.back_btn.clicked.connect(self.back_requested.emit)
        self.csv_btn = button("Export list (CSV)…")
        self.csv_btn.clicked.connect(self._export_csv)
        bar.addWidget(self.back_btn)
        bar.addWidget(self.csv_btn)
        bar.addStretch(1)
        self.generate_btn = button("Generate PDFs", "primary")
        self.generate_btn.clicked.connect(self.generate_requested.emit)
        bar.addWidget(self.generate_btn)
        left.addLayout(bar)

        self.preview = PreviewPane()
        self.preview.setFixedWidth(360)
        root.addWidget(self.preview)
        self.table.itemSelectionChanged.connect(self._on_selection)

    # ------------------------------------------------------------
    def load(self, result: AnalysisResult) -> None:
        self.result = result
        s = result.stats()
        self.tiles["PAGES"].set_value(s.pages)
        self.tiles["EBAY"].set_value(s.ebay_labels)
        self.tiles["TIKTOK"].set_value(s.tiktok_labels)
        self.tiles["INPOST"].set_value(s.inpost_labels)
        self.tiles["FLAGS"].set_value(s.review_pages)

        rows = result.exception_rows()
        self._row_pages = []
        self.table.setRowCount(len(rows))
        for n, row in enumerate(rows):
            pi = next(i for i, p in enumerate(result.pages) if p.prints_page == row.prints_page)
            self._row_pages.append(pi)
            status = QTableWidgetItem("Needs review" if row.needs_review else "Note")
            status.setData(PLATFORM_ROLE, "PENDING" if row.needs_review else "SKIPPED")
            cells = [status, QTableWidgetItem(row.filename), QTableWidgetItem(str(row.page_number)),
                     QTableWidgetItem(str(row.prints_page)), QTableWidgetItem(f"{row.kinds}: {row.reason}")]
            for col, item in enumerate(cells):
                if col >= 1:
                    item.setForeground(theme.color("text" if col == 4 else "muted"))
                self.table.setItem(n, col, item)
            self.table.setRowHeight(n, 44)
        self.stack.setCurrentWidget(self.table if rows else self.empty)
        self.preview.clear("Select a row to preview the page")
        if rows:
            self.table.selectRow(0)
        self.refresh_gate()

    def refresh_gate(self) -> None:
        """Enable Generate only when nothing is left undecided."""
        pending = len(self.result.pending_labels()) if self.result else 0
        if pending:
            self.banner.text.setText(f"{pending} label{'s' if pending != 1 else ''} still need a decision, "
                                     "so the PDFs cannot be generated yet.")
            self.banner.set_kind("danger")
            self.banner.action.setVisible(True)
            self.banner.setVisible(True)
        else:
            self.banner.action.setVisible(False)
            self.banner.setVisible(False)
        self.generate_btn.setEnabled(pending == 0)

    def _on_selection(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows or self.result is None:
            return
        page = self.result.pages[self._row_pages[rows[0]]]
        self.preview.show_source(page.path, page.page_number, None, f"{page.filename} · page {page.page_number}")

    def _export_csv(self) -> None:
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export flagged pages", "exceptions.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            pdf_processor.write_exceptions_csv(Path(path), self.result.exception_rows())
            self.message.emit("Exception list saved")
        except OSError as exc:
            self.message.emit(f"Could not save the file: {exc}")
