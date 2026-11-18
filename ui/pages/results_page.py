"""Step 3: every label in one table. Filter with chips, fix anything wrong, then continue."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QHBoxLayout, QHeaderView, QMenu, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import platforms
from core.models import AnalysisResult, LabelInfo, Platform, Status
from ui import theme
from ui.widgets import (PLATFORM_ROLE, Banner, Card, PlatformDelegate, PreviewPane, StatTile, button, label)

FILTERS = [("ALL", "All"), ("EBAY", "eBay"), ("TIKTOK", "TikTok"), ("INPOST", "InPost"),
           ("PENDING", "Needs decision"), ("SKIPPED", "Skipped")]
HOW = {"text": "Found in text", "ocr": "Read by OCR", "manual": "Chosen by you"}


def status_of(lab: LabelInfo) -> tuple[str, str]:
    """(filter key, display name) for a label's current state."""
    if lab.status is Status.CLASSIFIED and lab.platform is not None:
        return lab.platform.key, lab.platform.value
    if lab.status is Status.SKIPPED:
        return "SKIPPED", "Skipped"
    return "PENDING", "Needs decision"


class ResultsPage(QWidget):
    continue_requested = Signal()
    changed = Signal()                 # a label was reassigned
    message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.result: Optional[AnalysisResult] = None
        self._rows: list[tuple[int, int]] = []     # table row -> (page index, label index)
        self._filter = "ALL"

        root = QHBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 24)
        root.setSpacing(20)
        left = QVBoxLayout()
        left.setSpacing(14)
        root.addLayout(left, 1)

        left.addWidget(label("Results", "Title"))
        left.addWidget(label("Check the sorting. Click a row to see the label; use the buttons or the keys "
                             "E, T, I and S to move it.", "Subtitle", wrap=True))

        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tiles = {"EBAY": StatTile("eBay", "EBAY"), "TIKTOK": StatTile("TikTok", "TIKTOK"),
                      "INPOST": StatTile("InPost", "INPOST"), "PENDING": StatTile("Needs decision", "warn")}
        for t in self.tiles.values():
            tiles.addWidget(t, 1)
        left.addLayout(tiles)

        self.banner = Banner("", "", "Show them")
        self.banner.action.clicked.connect(lambda: self._set_filter("PENDING"))
        left.addWidget(self.banner)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.chips: dict[str, object] = {}
        for key, title in FILTERS:
            c = button(title)
            c.setProperty("chip", "true")
            c.setCheckable(True)
            c.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self.group.addButton(c)
            self.chips[key] = c
            chips.addWidget(c)
        chips.addStretch(1)
        self.chips["ALL"].setChecked(True)
        left.addLayout(chips)

        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(6, 6, 6, 6)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Result", "File", "Page", "Label", "How", "Note"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setItemDelegateForColumn(0, PlatformDelegate(self.table))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        head = self.table.horizontalHeader()
        for col, mode in enumerate((QHeaderView.ResizeMode.Fixed, QHeaderView.ResizeMode.Stretch,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch)):
            head.setSectionResizeMode(col, mode)
        self.table.setColumnWidth(0, 150)
        cl.addWidget(self.table)
        left.addWidget(card, 1)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(label("Move selected to", "Muted"))
        self.move_buttons: dict[str, object] = {}
        for platform in platforms.ORDER:
            b = button(f"{platform.value}", tooltip=f"Key {platform.code}")
            b.setProperty("platform", platform.key)
            b.clicked.connect(lambda _=False, p=platform: self._assign(p))
            bar.addWidget(b)
            self.move_buttons[platform.key] = b
        self.skip_btn = button("Skip", "ghost", tooltip="Key S. Stays in PRINTS, left out of the sorted files.")
        self.skip_btn.clicked.connect(lambda: self._assign(None))
        bar.addWidget(self.skip_btn)
        bar.addStretch(1)
        self.next_btn = button("Review exceptions", "primary")
        self.next_btn.clicked.connect(self.continue_requested.emit)
        bar.addWidget(self.next_btn)
        left.addLayout(bar)

        self.preview = PreviewPane()
        self.preview.setFixedWidth(360)
        root.addWidget(self.preview)

        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.customContextMenuRequested.connect(self._menu)
        for key, target in (("E", Platform.EBAY), ("T", Platform.TIKTOK), ("I", Platform.INPOST), ("S", None)):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda t=target: self._assign(t))

    # ------------------------------------------------------------ loading
    def load(self, result: AnalysisResult) -> None:
        self.result = result
        self._rows = [(pi, li) for pi, page in enumerate(result.pages) for li in range(len(page.labels))]
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self._rows))
        for row in range(len(self._rows)):
            self._fill_row(row)
        self.table.setUpdatesEnabled(True)
        self._set_filter("PENDING" if self._pending() else "ALL")
        self._recount()
        self.preview.clear()
        if self._rows:
            first = next((r for r in range(len(self._rows)) if not self.table.isRowHidden(r)), 0)
            self.table.selectRow(first)

    def pending_count(self) -> int:
        return self._pending()

    def show_pending(self) -> None:
        self._set_filter("PENDING")

    # ------------------------------------------------------------ table
    def _label(self, row: int) -> LabelInfo:
        assert self.result is not None
        pi, li = self._rows[row]
        return self.result.pages[pi].labels[li]

    def _fill_row(self, row: int) -> None:
        assert self.result is not None
        pi, li = self._rows[row]
        page = self.result.pages[pi]
        lab = page.labels[li]
        key, name = status_of(lab)
        pill = QTableWidgetItem(name)
        pill.setData(PLATFORM_ROLE, key)
        how = HOW.get(lab.method, "") if key in ("EBAY", "TIKTOK", "INPOST") else ""
        if lab.duplicate_of:
            note = f"Duplicate of {lab.duplicate_of}"
        elif key == "PENDING":
            note = lab.detail
        else:
            note = lab.evidence if lab.method != "manual" else ""
        cells = [pill, QTableWidgetItem(page.filename), QTableWidgetItem(str(page.page_number)),
                 QTableWidgetItem(f"{li + 1} of {len(page.labels)}" if len(page.labels) > 1 else "1 of 1"),
                 QTableWidgetItem(how), QTableWidgetItem(note)]
        for col, item in enumerate(cells):
            if col >= 2:
                item.setForeground(theme.color("muted"))
            self.table.setItem(row, col, item)
        self.table.setRowHeight(row, 38)

    def _pending(self) -> int:
        return sum(1 for r in range(len(self._rows)) if status_of(self._label(r))[0] == "PENDING")

    def _recount(self) -> None:
        counts = {key: 0 for key, _ in FILTERS}
        for r in range(len(self._rows)):
            key = status_of(self._label(r))[0]
            counts[key] += 1
            counts["ALL"] += 1
        for key, tile in self.tiles.items():
            tile.set_value(counts[key])
        for key, title in FILTERS:
            self.chips[key].setText(f"{title}  {counts[key]}")
        pending = counts["PENDING"]
        if pending:
            self.banner.text.setText(f"{pending} label{'s' if pending != 1 else ''} still need a decision. "
                                     "Generating is blocked until each one is assigned or skipped.")
            self.banner.set_kind("")
            self.banner.action.setVisible(True)
        else:
            self.banner.text.setText("Every label is assigned or skipped. You are ready to continue.")
            self.banner.set_kind("ok")
            self.banner.action.setVisible(False)

    def _set_filter(self, key: str) -> None:
        self._filter = key
        self.chips[key].setChecked(True)
        self._apply_filter()

    def _apply_filter(self) -> None:
        for r in range(len(self._rows)):
            hidden = self._filter != "ALL" and status_of(self._label(r))[0] != self._filter
            self.table.setRowHidden(r, hidden)

    # ------------------------------------------------------------ actions
    def _selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def _assign(self, platform: Optional[Platform]) -> None:
        rows = self._selected_rows()
        if not rows or self.result is None:
            return
        for r in rows:
            lab = self._label(r)
            if platform is None:
                lab.skip()
            else:
                lab.set_platform(platform, "manual")
            self._fill_row(r)
        noun = f"{len(rows)} label{'s' if len(rows) != 1 else ''}"
        self.message.emit(f"Skipped {noun}" if platform is None else f"Moved {noun} to {platform.value}")
        self._recount()
        self._apply_filter()
        last = rows[-1]
        nxt = next((r for r in range(last + 1, len(self._rows)) if not self.table.isRowHidden(r)), None)
        if nxt is None:
            nxt = next((r for r in range(len(self._rows)) if not self.table.isRowHidden(r)), None)
        if nxt is not None:
            self.table.selectRow(nxt)
            self.table.scrollToItem(self.table.item(nxt, 0))
        else:
            self.preview.clear()
        self.changed.emit()

    def _on_selection(self) -> None:
        rows = self._selected_rows()
        if not rows or self.result is None:
            return
        pi, li = self._rows[rows[0]]
        page = self.result.pages[pi]
        lab = page.labels[li]
        caption = f"{page.filename} · page {page.page_number}"
        if len(page.labels) > 1:
            caption += f" · label {li + 1} of {len(page.labels)}"
        self.preview.show_source(page.path, page.page_number, lab.rect, caption)

    def _menu(self, pos) -> None:
        if not self._selected_rows():
            return
        menu = QMenu(self)
        for platform in platforms.ORDER:
            menu.addAction(f"Move to {platform.value}", lambda p=platform: self._assign(p))
        menu.addSeparator()
        menu.addAction("Skip", lambda: self._assign(None))
        menu.exec(self.table.viewport().mapToGlobal(pos))
