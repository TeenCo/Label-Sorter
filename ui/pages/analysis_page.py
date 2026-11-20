"""Step 2: live view of the analysis. When a label cannot be classified safely the analysis
pauses right here and asks which platform it is (no popup, no terminal)."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QProgressBar, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import platforms
from core.models import SKIP_CODE, AskContext, Platform, Progress
from ui import theme
from ui.widgets import (PLATFORM_ROLE, Card, PlatformDelegate, PreviewPane, StatTile, animate_progress, button,
                        fade_in, label, repolish, set_state, stagger_in)
from ui.workers import LabelEvent, PreviewFrame

FEED_LIMIT = 150


class AnalysisPage(QWidget):
    decided = Signal(object)          # "E" / "T" / "I" / "S", or None = decide later
    cancel_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._asking = False
        self._counts = {"EBAY": 0, "TIKTOK": 0, "INPOST": 0, "OPEN": 0}

        root = QHBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 24)
        root.setSpacing(20)

        self.preview = PreviewPane()
        self.preview.setMinimumWidth(320)
        root.addWidget(self.preview, 5)
        self.split_root, self.preview_width = root, None

        right = QVBoxLayout()
        right.setSpacing(14)
        root.addLayout(right, 6)

        # ---- status
        self.status_card = Card()
        sc = QVBoxLayout(self.status_card)
        sc.setContentsMargins(18, 16, 18, 16)
        sc.setSpacing(6)
        self.title = label("Analyzing labels", "Title")
        self.detail = label("Starting…", "Subtitle")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.totals = label("", "Faint")
        for w in (self.title, self.detail):
            sc.addWidget(w)
        sc.addSpacing(6)
        sc.addWidget(self.bar)
        sc.addWidget(self.totals)
        right.addWidget(self.status_card)

        # ---- live counters
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tiles = {
            "EBAY": StatTile("eBay", "EBAY"),
            "TIKTOK": StatTile("TikTok", "TIKTOK"),
            "INPOST": StatTile("InPost", "INPOST"),
            "OPEN": StatTile("Skipped or later", "faint"),
        }
        for tile in self.tiles.values():
            tiles.addWidget(tile, 1)
        right.addLayout(tiles)

        # ---- decision panel (hidden until a label needs you)
        self.decision = Card()
        self.decision.setProperty("state", "attention")
        dc = QVBoxLayout(self.decision)
        dc.setContentsMargins(18, 16, 18, 16)
        dc.setSpacing(8)
        self.q_title = label("Which platform is this label?", "CardTitle")
        self.q_reason = label("", "Muted", wrap=True)
        self.q_text = label("", "Faint", wrap=True)
        dc.addWidget(self.q_title)
        dc.addWidget(self.q_reason)
        dc.addWidget(self.q_text)
        choices = QHBoxLayout()
        choices.setSpacing(10)
        self.choice_buttons: dict[Platform, object] = {}
        for platform in platforms.ORDER:
            b = button(f"{platform.value}   {platform.code}", tooltip=f"Press {platform.code}")
            b.setProperty("platform", platform.key)
            b.setProperty("big", "true")
            b.clicked.connect(lambda _=False, c=platform.code: self._answer(c))
            choices.addWidget(b, 1)
            self.choice_buttons[platform] = b
        dc.addLayout(choices)
        more = QHBoxLayout()
        self.skip_btn = button("Skip this label   S", "ghost", tooltip="Press S. Stays in PRINTS, left out of the sorted files.")
        self.later_btn = button("Decide later   L", "ghost", tooltip="Press L. Continue now and settle it in Results.")
        self.skip_btn.clicked.connect(lambda: self._answer(SKIP_CODE))
        self.later_btn.clicked.connect(lambda: self._answer(None))
        more.addWidget(self.skip_btn)
        more.addWidget(self.later_btn)
        more.addStretch(1)
        dc.addLayout(more)
        self.decision.hide()
        right.addWidget(self.decision)

        # ---- live feed
        feed_card = Card()
        fc = QVBoxLayout(feed_card)
        fc.setContentsMargins(6, 12, 6, 6)
        fc.setSpacing(2)
        fc.addWidget(label("  Latest results", "CardTitle"))
        self.feed = QTableWidget(0, 3)
        self.feed.setHorizontalHeaderLabels(["Result", "Label", "How it was decided"])
        self.feed.verticalHeader().setVisible(False)
        self.feed.setShowGrid(False)
        self.feed.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.feed.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.feed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.feed.setItemDelegateForColumn(0, PlatformDelegate(self.feed))
        head = self.feed.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.feed.setColumnWidth(0, 150)
        fc.addWidget(self.feed, 1)
        right.addWidget(feed_card, 1)

        # ---- footer
        foot = QHBoxLayout()
        self.log_label = label("", "Faint")
        foot.addWidget(self.log_label, 1)
        self.cancel_btn = button("Cancel analysis", "ghost")
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        foot.addWidget(self.cancel_btn)
        right.addLayout(foot)

        for key, handler in (("E", Platform.EBAY.code), ("T", Platform.TIKTOK.code), ("I", Platform.INPOST.code),
                             ("S", SKIP_CODE), ("L", None)):
            sc_ = QShortcut(QKeySequence(key), self)
            sc_.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc_.activated.connect(lambda code=handler: self._answer(code) if self._asking else None)

    # ------------------------------------------------------------ lifecycle
    def begin(self) -> None:
        self._asking = False
        self._counts = {k: 0 for k in self._counts}
        for tile in self.tiles.values():
            tile.set_value(0)
        self.feed.setRowCount(0)
        self.decision.hide()
        self.preview.clear("Waiting for the first page…")
        self.preview.set_attention(False)
        self.title.setText("Analyzing labels")
        self.detail.setText("Starting…")
        self.totals.setText("")
        self.bar.setValue(0)
        set_state(self.bar, "")
        self.log_label.setText("")
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)
        stagger_in(list(self.tiles.values()))

    def finish(self) -> None:
        self._asking = False
        self.decision.hide()
        self.preview.set_attention(False)
        self.title.setText("Analysis complete")
        self.detail.setText("Review the results, fix anything that looks wrong, then generate the PDFs.")
        animate_progress(self.bar, 100)
        set_state(self.bar, "ok")
        self.cancel_btn.setVisible(False)

    def set_log(self, text: str) -> None:
        self.log_label.setText(text)

    # ------------------------------------------------------------ events from the worker
    def on_progress(self, p: Progress) -> None:
        if self._asking:
            return
        self.detail.setText(f"{p.filename} · page {p.page_no} of {p.page_total} (file {p.file_no} of {p.file_total})")
        self.totals.setText(f"{p.done} of {p.total} pages checked")
        animate_progress(self.bar, int(100 * p.done / max(p.total, 1)))

    def on_preview(self, frame: PreviewFrame) -> None:
        if not self._asking:
            self.preview.show_png(frame.png, frame.caption)

    def on_label(self, ev: LabelEvent) -> None:
        if ev.platform_key in self._counts:
            self._counts[ev.platform_key] += 1
        else:
            self._counts["OPEN"] += 1
        for key, tile in self.tiles.items():
            tile.set_value(self._counts[key])
        self.feed.insertRow(0)
        pill = QTableWidgetItem(ev.platform_name)
        pill.setData(PLATFORM_ROLE, ev.platform_key)
        where = f"{ev.filename} · page {ev.page_number}" + (f" · label {ev.label_number}/{ev.label_total}" if ev.label_total > 1 else "")
        how = {"text": "Found in text", "ocr": "Read by OCR", "manual": "You chose"}.get(ev.method, ev.note)
        self.feed.setItem(0, 0, pill)
        self.feed.setItem(0, 1, QTableWidgetItem(where))
        note = QTableWidgetItem(how if ev.method else ev.note)
        note.setForeground(theme.color("muted"))
        self.feed.setItem(0, 2, note)
        self.feed.setRowHeight(0, 36)
        while self.feed.rowCount() > FEED_LIMIT:
            self.feed.removeRow(self.feed.rowCount() - 1)

    def on_ask(self, ctx: AskContext, frame: PreviewFrame) -> None:
        self._asking = True
        self.title.setText("Waiting for your decision")
        where = f"{ctx.filename} · page {ctx.page_number}"
        if ctx.label_total > 1:
            where += f" · label {ctx.label_number} of {ctx.label_total}"
        self.detail.setText(where)
        set_state(self.bar, "attention")
        self.preview.show_png(frame.png, frame.caption, frame.source)
        self.preview.set_attention(True)
        self.q_title.setText("This label names more than one platform" if ctx.ambiguous
                             else "No platform name found on this label")
        reason = ctx.reason[:1].upper() + ctx.reason[1:]
        self.q_reason.setText(f"{reason}. Check the preview, then choose where it belongs.")
        self.q_text.setText(f"Text on the label: {ctx.excerpt}" if ctx.excerpt else "")
        self.q_text.setVisible(bool(ctx.excerpt))
        for platform, b in self.choice_buttons.items():
            hit = platform in ctx.candidates
            b.setProperty("suggested", "true" if hit else "false")
            b.setText(f"{platform.value}   {platform.code}" + ("   (named on label)" if hit and ctx.ambiguous else ""))
            repolish(b)
        self.decision.show()
        fade_in(self.decision)
        self.choice_buttons[platforms.ORDER[0]].setFocus()

    # ------------------------------------------------------------ user answer
    def _answer(self, code: Optional[str]) -> None:
        if not self._asking:
            return
        self._asking = False
        self.decision.hide()
        self.preview.set_attention(False)
        self.title.setText("Analyzing labels")
        set_state(self.bar, "")
        self.decided.emit(code)
