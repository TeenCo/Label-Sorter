"""Left navigation: the five steps, their state, and a running summary of the batch."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QAbstractButton, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from core import config
from ui import theme
from ui.widgets import hline, label

STEPS = ["Files", "Analysis", "Results", "Exceptions", "Output"]


class StepButton(QAbstractButton):
    """One step. States: locked (not reachable yet), todo, active (current), done."""

    def __init__(self, number: int, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.number, self.title = number, title
        self._state = "locked"
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_state("locked")

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
        box = QRectF(self.rect()).adjusted(10, 2, -10, -2)
        active, done, locked = self._state == "active", self._state == "done", self._state == "locked"
        if active:
            fill = QColor(theme.PALETTE["accent"])
            fill.setAlphaF(0.14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(box, 8, 8)
        elif self.underMouse() and not locked:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("hover"))
            p.drawRoundedRect(box, 8, 8)
        if self.hasFocus():
            p.setPen(theme.color("accent"))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(box, 8, 8)

        centre = QPointF(box.left() + 20, box.center().y())
        radius = 10.0
        if done:
            ring = QColor(theme.PALETTE["ok"])
            bg = QColor(ring)
            bg.setAlphaF(0.18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawEllipse(centre, radius, radius)
            mark, mark_color = "✓", ring
        else:
            ring = theme.color("accent") if active else theme.color("border" if locked else "faint")
            p.setPen(ring)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(centre, radius, radius)
            mark = str(self.number)
            mark_color = theme.color("accent") if active else theme.color("faint" if locked else "muted")
        small = QFont(self.font())
        small.setPointSizeF(8.5)
        small.setBold(True)
        p.setFont(small)
        p.setPen(mark_color)
        p.drawText(QRectF(centre.x() - radius, centre.y() - radius, radius * 2, radius * 2),
                   int(Qt.AlignmentFlag.AlignCenter), mark)

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


class Sidebar(QFrame):
    step_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(232)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 22, 8, 16)
        lay.setSpacing(2)

        brand = QHBoxLayout()
        brand.setContentsMargins(14, 0, 8, 0)
        brand.addWidget(label("Label Sorter", "Brand"))
        brand.addStretch(1)
        lay.addLayout(brand)
        lay.addSpacing(18)

        self.buttons: list[StepButton] = []
        for i, title in enumerate(STEPS):
            b = StepButton(i + 1, title)
            b.clicked.connect(lambda _=False, n=i: self.step_clicked.emit(n))
            lay.addWidget(b)
            self.buttons.append(b)
        lay.addStretch(1)

        self.summary = QFrame()
        sl = QVBoxLayout(self.summary)
        sl.setContentsMargins(14, 0, 14, 0)
        sl.setSpacing(6)
        sl.addWidget(hline())
        sl.addSpacing(6)
        sl.addWidget(label("This batch", "Faint"))
        self._values = {}
        for key, name in (("EBAY", "eBay"), ("TIKTOK", "TikTok"), ("INPOST", "InPost"), ("OPEN", "Undecided")):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_Dot("warn" if key == "OPEN" else key))
            row.addWidget(label(name, "Muted"), 1)
            value = label("0")
            row.addWidget(value)
            self._values[key] = value
            sl.addLayout(row)
        lay.addWidget(self.summary)
        self.summary.hide()
        lay.addSpacing(10)
        lay.addWidget(label(f"  Version {config.APP_VERSION}", "Faint"))

    def set_states(self, states: list[str]) -> None:
        for button_, state in zip(self.buttons, states):
            button_.set_state(state)

    def set_summary(self, ebay: int, tiktok: int, inpost: int, undecided: int) -> None:
        for key, value in (("EBAY", ebay), ("TIKTOK", tiktok), ("INPOST", inpost), ("OPEN", undecided)):
            self._values[key].setText(str(value))
        self.summary.show()

    def hide_summary(self) -> None:
        self.summary.hide()
