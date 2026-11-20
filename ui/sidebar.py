"""Left navigation: the five steps, their state, and a running summary of the batch."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from core import config
from ui import theme
from ui.widgets import hline, label

STEPS = ["Files", "Analysis", "Results", "Exceptions", "Output"]


class StepButton(QAbstractButton):
    """One step. States: locked (not reachable yet), todo, active (current), done.
    The active highlight is drawn by the sidebar so it can slide between steps."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self._state = "locked"
        self._compact = False
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(title)
        self.set_state("locked")

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.update()

    def set_state(self, state: str) -> None:
        self._state = state
        self.setEnabled(state != "locked")
        self.setCursor(Qt.CursorShape.PointingHandCursor if state != "locked" else Qt.CursorShape.ArrowCursor)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 42)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(8, 2, -8, -2)
        active, done, locked = self._state == "active", self._state == "done", self._state == "locked"
        if not active and self.underMouse() and not locked:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("hover"))
            p.drawRoundedRect(box, 8, 8)
        if self.hasFocus():
            p.setPen(QPen(theme.color("accent"), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(box, 8, 8)

        # state mark: tick (done), solid dot (active), ring (todo), faint ring (locked)
        centre = QPointF(box.left() + 20, box.center().y()) if not self._compact else QPointF(box.center().x(), box.center().y())
        if done:
            p.setPen(QPen(theme.color("ok"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPolyline([QPointF(centre.x() - 4.5, centre.y()), QPointF(centre.x() - 1.2, centre.y() + 3.5),
                            QPointF(centre.x() + 5, centre.y() - 3.5)])
        elif active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("accent"))
            p.drawEllipse(centre, 4.5, 4.5)
        else:
            p.setPen(QPen(theme.color("border" if locked else "faint"), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(centre, 4.5, 4.5)

        if self._compact:
            return
        font = QFont(self.font())
        font.setBold(active)
        p.setFont(font)
        p.setPen(theme.color("text" if active else ("faint" if locked else "muted")))
        p.drawText(QRectF(box.left() + 40, box.top(), box.width() - 44, box.height()),
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self.title)


class _Dot(QFrame):
    def __init__(self, key: str) -> None:
        super().__init__()
        self.setFixedSize(8, 8)
        self._color = QColor(theme.PALETTE.get(key, theme.PALETTE["faint"]))

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(0, 0, 8, 8)


FULL_WIDTH = 232
RAIL_WIDTH = 64


class Sidebar(QFrame):
    step_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._width = FULL_WIDTH
        self._compact = False
        self._hl_y = 0.0
        self._hl_on = False
        self._has_summary = False
        self.setFixedWidth(FULL_WIDTH)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 22, 0, 16)
        lay.setSpacing(2)

        self.brand = label("Label Sorter", "Brand")
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(22, 0, 8, 0)
        brand_row.addWidget(self.brand)
        brand_row.addStretch(1)
        lay.addLayout(brand_row)
        lay.addSpacing(18)

        self.buttons: list[StepButton] = []
        for i, title in enumerate(STEPS):
            b = StepButton(title)
            b.clicked.connect(lambda _=False, n=i: self.step_clicked.emit(n))
            lay.addWidget(b)
            self.buttons.append(b)
        lay.addStretch(1)

        self.summary = QFrame()
        sl = QVBoxLayout(self.summary)
        sl.setContentsMargins(22, 0, 22, 0)
        sl.setSpacing(6)
        self._values = {}
        self._rows = []
        for key, name in (("EBAY", "eBay"), ("TIKTOK", "TikTok"), ("INPOST", "InPost"), ("OPEN", "Undecided")):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_Dot("warn" if key == "OPEN" else key))
            name_label = label(name, "Muted")
            row.addWidget(name_label, 1)
            value = label("0")
            row.addWidget(value)
            self._values[key] = value
            self._rows.append(name_label)
            sl.addLayout(row)
        lay.addWidget(self.summary)
        self.summary.hide()
        lay.addSpacing(10)
        self.version = label(f"Version {config.APP_VERSION}", "Faint")
        ver_row = QHBoxLayout()
        ver_row.setContentsMargins(22, 0, 0, 0)
        ver_row.addWidget(self.version)
        lay.addLayout(ver_row)

        self._width_anim = QPropertyAnimation(self, b"railWidth", self)
        self._width_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._hl_anim = QPropertyAnimation(self, b"highlightY", self)
        self._hl_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    # ---- responsive rail: full width on large windows, icon-only rail on narrow ones
    def get_rail_width(self) -> int:
        return self._width

    def set_rail_width(self, value: int) -> None:
        self._width = int(value)
        self.setFixedWidth(self._width)

    railWidth = Property(int, get_rail_width, set_rail_width)

    def set_compact(self, compact: bool, animate: bool = True) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        for b in self.buttons:
            b.set_compact(compact)
        for w in (self.brand, self.version, *self._rows):
            w.setVisible(not compact)
        for value in self._values.values():
            value.setVisible(not compact)
        self.summary.setVisible(self._has_summary and not compact)
        target = RAIL_WIDTH if compact else FULL_WIDTH
        if animate and self.isVisible():
            self._width_anim.stop()
            self._width_anim.setDuration(theme.MOVE_MS)
            self._width_anim.setStartValue(self._width)
            self._width_anim.setEndValue(target)
            self._width_anim.start()
        else:
            self.set_rail_width(target)

    # ---- sliding highlight (moves inside the window, so it eases in and out)
    def get_highlight_y(self) -> float:
        return self._hl_y

    def set_highlight_y(self, value: float) -> None:
        self._hl_y = float(value)
        self.update()

    highlightY = Property(float, get_highlight_y, set_highlight_y)

    def _move_highlight(self, index: int | None) -> None:
        if index is None:
            self._hl_on = False
            self.update()
            return
        target = float(self.buttons[index].y())
        if not self._hl_on:
            self._hl_on = True
            self.set_highlight_y(target)
            return
        self._hl_anim.stop()
        self._hl_anim.setDuration(theme.MOVE_MS)
        self._hl_anim.setStartValue(self._hl_y)
        self._hl_anim.setEndValue(target)
        self._hl_anim.start()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._hl_on:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(theme.PALETTE["accent"])
        fill.setAlphaF(0.12)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(8, self._hl_y + 2, self.width() - 16, 38), 8, 8)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        for i, b in enumerate(self.buttons):
            if b._state == "active":
                self._hl_anim.stop()
                self.set_highlight_y(float(b.y()))

    def set_states(self, states: list[str]) -> None:
        active = None
        for i, (button_, state) in enumerate(zip(self.buttons, states)):
            button_.set_state(state)
            if state == "active":
                active = i
        self._move_highlight(active)

    def set_summary(self, ebay: int, tiktok: int, inpost: int, undecided: int) -> None:
        for key, value in (("EBAY", ebay), ("TIKTOK", tiktok), ("INPOST", inpost), ("OPEN", undecided)):
            self._values[key].setText(str(value))
        self._has_summary = True
        self.summary.setVisible(not self._compact)

    def hide_summary(self) -> None:
        self._has_summary = False
        self.summary.hide()
