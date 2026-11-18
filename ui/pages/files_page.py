"""Step 1: choose the PDFs, check their order, choose where the results go."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import file_manager
from ui import theme
from ui.widgets import Card, DropZone, button, label


class FilesPage(QWidget):
    start_requested = Signal()
    message = Signal(str)             # short notices for the toast

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._files: list[Path] = []
        self._out_dir: Optional[Path] = None
        self._last_dir = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 24)
        root.setSpacing(16)
        root.addWidget(label("Add your label PDFs", "Title"))
        root.addWidget(label("The order below is the order of every page in the output files. "
                             "Oldest download first is the default.", "Subtitle", wrap=True))

        self.drop = DropZone()
        self.drop.files_dropped.connect(self.add_files)
        self.drop.browse_requested.connect(self.browse)
        root.addWidget(self.drop)

        # ---- file list card
        self.list_card = Card()
        card = QVBoxLayout(self.list_card)
        card.setContentsMargins(6, 6, 6, 6)
        card.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 6, 10, 6)
        self.count_label = label("", "Muted")
        bar.addWidget(self.count_label, 1)
        self.by_time = button("Sort by download time", "ghost")
        self.by_name = button("Sort by name", "ghost")
        self.up = button("Move up", "ghost", tooltip="Alt+Up")
        self.down = button("Move down", "ghost", tooltip="Alt+Down")
        self.remove = button("Remove", "ghost", tooltip="Delete")
        for b in (self.by_time, self.by_name, self.up, self.down, self.remove):
            bar.addWidget(b)
        card.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "File", "Downloaded", "Size"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        card.addWidget(self.table, 1)
        root.addWidget(self.list_card, 1)

        # ---- footer
        foot = QHBoxLayout()
        foot.setSpacing(10)
        foot.addWidget(label("Save results to", "Muted"))
        self.out_edit = QLineEdit()
        self.out_edit.setReadOnly(True)
        self.out_edit.setMinimumWidth(320)
        foot.addWidget(self.out_edit, 1)
        self.out_btn = button("Change…")
        foot.addWidget(self.out_btn)
        foot.addSpacing(16)
        self.start_btn = button("Start analysis", "primary")
        foot.addWidget(self.start_btn)
        root.addLayout(foot)

        self.by_time.clicked.connect(lambda: self._sort("time"))
        self.by_name.clicked.connect(lambda: self._sort("name"))
        self.up.clicked.connect(lambda: self._move(-1))
        self.down.clicked.connect(lambda: self._move(1))
        self.remove.clicked.connect(self._remove)
        self.out_btn.clicked.connect(self.choose_out_dir)
        self.start_btn.clicked.connect(self.start_requested.emit)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        for keys, fn in (("Delete", self._remove), ("Alt+Up", lambda: self._move(-1)), ("Alt+Down", lambda: self._move(1))):
            sc = QShortcut(QKeySequence(keys), self.table)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(fn)
        self._refresh()

    # ------------------------------------------------------------ public
    def files(self) -> list[Path]:
        return list(self._files)

    def out_dir(self) -> Optional[Path]:
        return self._out_dir or (file_manager.default_output_dir(self._files[0]) if self._files else None)

    def clear(self) -> None:
        self._files, self._out_dir = [], None
        self._refresh()

    def browse(self) -> None:
        picked, _ = QFileDialog.getOpenFileNames(self, "Select the shipping label PDFs", self._last_dir,
                                                 "PDF files (*.pdf *.PDF)")
        if picked:
            self.add_files(picked)

    def add_files(self, paths: list[str]) -> None:
        if paths:
            self._last_dir = str(Path(paths[0]).parent)
        wanted = file_manager.normalize_selection([*self._files, *paths])
        known = {str(p) for p in self._files}
        new = [p for p in wanted if str(p) not in known]
        if not new:
            self.message.emit("Those files are already in the list")
            return
        if self._files:
            self._files += file_manager.order_by_download_time(new)     # keep the order the user already set
        else:
            self._files = file_manager.order_by_download_time(new)
        self._refresh()
        self.message.emit(f"Added {len(new)} file{'s' if len(new) != 1 else ''}")

    def choose_out_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose the output folder", str(self.out_dir() or ""))
        if folder:
            self._out_dir = Path(folder)
            self._refresh()

    # ------------------------------------------------------------ actions
    def _selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def _sort(self, mode: str) -> None:
        self._files = (file_manager.order_by_download_time(self._files) if mode == "time"
                       else file_manager.order_by_name(self._files))
        self._refresh()
        self.message.emit("Sorted by download time" if mode == "time" else "Sorted by name")

    def _move(self, delta: int) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        for i in (rows if delta < 0 else reversed(rows)):
            j = i + delta
            if 0 <= j < len(self._files) and j not in rows:
                self._files[i], self._files[j] = self._files[j], self._files[i]
        moved = [min(max(i + delta, 0), len(self._files) - 1) for i in rows]
        self._refresh(select=moved)

    def _remove(self) -> None:
        rows = set(self._selected_rows())
        if not rows:
            return
        self._files = [p for i, p in enumerate(self._files) if i not in rows]
        self._refresh()
        self.message.emit(f"Removed {len(rows)} file{'s' if len(rows) != 1 else ''}")

    # ------------------------------------------------------------ view
    def _refresh(self, select: Optional[list[int]] = None) -> None:
        has = bool(self._files)
        self.drop.set_compact(has)
        self.list_card.setVisible(has)
        self.table.setRowCount(len(self._files))
        for i, path in enumerate(self._files):
            try:
                when = file_manager.download_time(path).strftime("%Y-%m-%d  %H:%M")
                size = f"{path.stat().st_size / 1024:,.0f} KB"
            except OSError:
                when, size = "unknown", "unknown"
            for col, text in enumerate((str(i + 1), path.name, when, size)):
                item = QTableWidgetItem(text)
                item.setToolTip(str(path))
                if col in (0, 2, 3):
                    item.setForeground(theme.color("muted"))
                self.table.setItem(i, col, item)
            self.table.setRowHeight(i, 38)
        if select:
            model, sel_model = self.table.model(), self.table.selectionModel()
            sel_model.clearSelection()
            for i in select:
                sel_model.select(model.index(i, 0), QItemSelectionModel.SelectionFlag.Select
                                 | QItemSelectionModel.SelectionFlag.Rows)
        n = len(self._files)
        self.count_label.setText(f"{n} file{'s' if n != 1 else ''}")
        out = self.out_dir()
        self.out_edit.setText(str(out) if out else "")
        self.out_edit.setPlaceholderText("Same folder as the first PDF")
        self.start_btn.setEnabled(has)
        self.start_btn.setText(f"Analyze {n} file{'s' if n != 1 else ''}" if has else "Start analysis")
        self._update_buttons()

    def _update_buttons(self) -> None:
        sel = bool(self._selected_rows())
        for b in (self.up, self.down, self.remove):
            b.setEnabled(sel)
        two = len(self._files) > 1
        self.by_time.setEnabled(two)
        self.by_name.setEnabled(two)
