"""Small reusable widgets shared by all pages."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import (QApplication, QBoxLayout, QCheckBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QSizePolicy, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QVBoxLayout, QWidget)

from core.rendering import render_page_png
from ui import theme


# ---------------------------------------------------------------- helpers
def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class PressButton(QPushButton):
    """A button that shrinks to 0.97 while pressed (snappy feedback, no bounce)."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._rendering = False
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)   # keyboard focus ring only, not after a click

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self.isDown() or self._rendering or not self.isEnabled():
            super().paintEvent(event)
            return
        dpr = self.devicePixelRatioF()
        pix = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.GlobalColor.transparent)
        self._rendering = True
        try:
            self.render(pix, QPoint(), QRegion(self.rect()), QWidget.RenderFlag.DrawChildren)
        finally:
            self._rendering = False
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(self.width() / 2, self.height() / 2)
        p.scale(theme.PRESS_SCALE, theme.PRESS_SCALE)
        p.translate(-self.width() / 2, -self.height() / 2)
        p.drawPixmap(0, 0, pix)


def button(text: str, variant: str = "", parent: Optional[QWidget] = None, tooltip: str = "") -> QPushButton:
    b = PressButton(text, parent)
    if variant:
        b.setProperty("variant", variant)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def label(text: str = "", name: str = "", wrap: bool = False, parent: Optional[QWidget] = None) -> QLabel:
    lab = QLabel(text, parent)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    return line


def fade_in(widget: QWidget, duration_ms: int = theme.ENTER_MS, delay_ms: int = 0) -> None:
    """Short fade used when a page appears. The effect is removed afterwards (keeps text crisp)."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._fade_anim = anim  # keep a reference
    if delay_ms > 0:
        QTimer.singleShot(delay_ms, anim.start)
    else:
        anim.start()


_QWIDGETSIZE_MAX = 16777215


def adapt_split(root: QBoxLayout, preview: QWidget, narrow: bool, wide_width: Optional[int] = None,
                narrow_height: int = 240) -> None:
    """Side-by-side layout on wide windows; stacked (preview below or above) when the window is narrow."""
    root.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
    root.setContentsMargins(*((20, 20, 20, 16) if narrow else (36, 30, 36, 24)))
    if narrow:
        preview.setMinimumWidth(0)
        preview.setMaximumWidth(_QWIDGETSIZE_MAX)
        preview.setFixedHeight(narrow_height)
    else:
        preview.setMinimumHeight(0)
        preview.setMaximumHeight(_QWIDGETSIZE_MAX)
        if wide_width:
            preview.setFixedWidth(wide_width)
        else:
            preview.setMinimumWidth(320)
            preview.setMaximumWidth(_QWIDGETSIZE_MAX)


def stagger_in(widgets, step_ms: int = theme.STAGGER_MS) -> None:
    """Fade a group in one after another, 30 ms apart."""
    for i, w in enumerate(widgets):
        fade_in(w, delay_ms=i * step_ms)


def crossfade(stack: QWidget, snap: QPixmap, new: QWidget) -> None:
    """Old and new page overlap: a snapshot of the old page (taken before the switch) fades out,
    20% faster than the new page fades in, so there is never an empty frame in between."""
    overlay = QLabel(stack)
    overlay.setPixmap(snap)
    overlay.setGeometry(stack.rect())
    overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    overlay.show()
    overlay.raise_()
    effect = QGraphicsOpacityEffect(overlay)
    overlay.setGraphicsEffect(effect)
    out = QPropertyAnimation(effect, b"opacity", overlay)
    out.setDuration(theme.EXIT_MS)
    out.setStartValue(1.0)
    out.setEndValue(0.0)
    out.setEasingCurve(QEasingCurve.Type.OutCubic)
    out.finished.connect(overlay.deleteLater)
    out.start()
    overlay._anim = out
    fade_in(new)


def pulse(widget: QWidget) -> None:
    """Quick brightness pulse used to confirm success."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(420)
    anim.setKeyValueAt(0.0, 0.45)
    anim.setKeyValueAt(0.35, 1.0)
    anim.setKeyValueAt(0.55, 0.8)
    anim.setKeyValueAt(1.0, 1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start()
    widget._pulse_anim = anim


def animate_progress(bar: QProgressBar, value: int, duration_ms: int = 180) -> None:
    anim = getattr(bar, "_anim", None)
    if anim is None:
        anim = QPropertyAnimation(bar, b"value", bar)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        bar._anim = anim
    anim.stop()
    anim.setDuration(duration_ms)
    anim.setStartValue(bar.value())
    anim.setEndValue(value)
    anim.start()


def set_state(widget: QWidget, state: str) -> None:
    widget.setProperty("state", state)
    repolish(widget)


# ---------------------------------------------------------------- cards
class Card(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")


class Banner(QFrame):
    """A message strip: ``kind`` is warn (default), danger, ok or info. Optional action button."""

    def __init__(self, text: str = "", kind: str = "", action_text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(12)
        self.text = label(text, wrap=True)
        lay.addWidget(self.text, 1)
        self.action = button(action_text, parent=self)
        self.action.setVisible(bool(action_text))
        lay.addWidget(self.action)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        self.setProperty("kind", kind)
        repolish(self)


class StatTile(QFrame):
    """Label + big number. ``accent_key`` is a palette name (platform keys work too)."""

    def __init__(self, title: str, accent_key: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._accent = accent_key
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        self.title = label(title, "Muted")
        self.value = label("0", "BigNumber")
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        self.setMinimumWidth(120)

    def set_value(self, value: int | str) -> None:
        self.value.setText(str(value))

    def set_title(self, title: str) -> None:
        self.title.setText(title)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._accent not in theme.PALETTE:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.PALETTE[self._accent]))
        p.drawRoundedRect(QRectF(0, 14, 3, self.height() - 28), 1.5, 1.5)


# ---------------------------------------------------------------- preview
class PreviewPane(QFrame):
    """Shows a rendered page. Screen only: output PDFs never use these images."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Preview")
        self._pix: Optional[QPixmap] = None
        self._source: Optional[tuple] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)
        top = QHBoxLayout()
        self.caption = label("Preview", "Muted")
        top.addWidget(self.caption, 1)
        self.full_check = QCheckBox("Show full page")
        self.full_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.full_check.toggled.connect(self._render_source)
        self.full_check.setEnabled(False)
        top.addWidget(self.full_check)
        lay.addLayout(top)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(80, 80)
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image.setWordWrap(True)
        lay.addWidget(self.image, 1)
        self.clear()

    def set_attention(self, on: bool) -> None:
        set_state(self, "attention" if on else "")

    def clear(self, message: str = "Select a label to preview it") -> None:
        self._pix = None
        self._source = None
        self.full_check.setEnabled(False)
        self.caption.setText("Preview")
        self.image.setPixmap(QPixmap())
        self.image.setText(message)
        self.image.setObjectName("Faint")
        repolish(self.image)

    def show_png(self, png: bytes, caption: str = "", source: Optional[tuple] = None) -> None:
        pix = QPixmap()
        if not png or not pix.loadFromData(png):
            self.clear("Preview not available")
            return
        self._pix = pix
        self._source = source
        self._caption = caption
        self.caption.setText(caption or "Preview")
        self.full_check.setEnabled(source is not None)
        self.image.setText("")
        self._rescale()

    def show_source(self, path: Path, page_number: int, rect, caption: str = "") -> None:
        """Render in the UI thread. Only call while no analysis worker is running."""
        self._source = (path, page_number, rect)
        self._caption = caption
        self.full_check.setEnabled(True)
        self._render_source()

    def _render_source(self, *_args) -> None:
        if not self._source:
            return
        path, page_number, rect = self._source
        clip = None if self.full_check.isChecked() else rect
        try:
            png = render_page_png(path, page_number, clip)
        except Exception as exc:  # noqa: BLE001
            self._pix = None
            self.image.setPixmap(QPixmap())
            self.image.setText(f"Preview not available:\n{exc}")
            return
        pix = QPixmap()
        pix.loadFromData(png)
        self._pix = pix
        self.caption.setText(getattr(self, "_caption", "") or f"{Path(path).name} · page {page_number}")
        self.image.setText("")
        self._rescale()

    def _rescale(self) -> None:
        if self._pix is None or self._pix.isNull():
            return
        dpr = self.devicePixelRatioF()
        size = self.image.size()
        if size.width() < 4 or size.height() < 4:
            return
        target = QSize(int(size.width() * dpr), int(size.height() * dpr))
        scaled = self._pix.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        self.image.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rescale()


# ---------------------------------------------------------------- drop zone
class DropZone(QFrame):
    files_dropped = Signal(list)
    browse_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(4)
        self.title = label("Drop your label PDFs here", "CardTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint = label("or click to browse. You can add files more than once.", "Muted")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.title)
        lay.addWidget(self.hint)
        self.set_compact(False)

    def set_compact(self, compact: bool) -> None:
        self.setFixedHeight(64 if compact else 190)
        self.hint.setVisible(not compact)
        self.title.setText("Drop more PDFs here, or click to add" if compact else "Drop your label PDFs here")

    @staticmethod
    def _pdfs(event) -> list[str]:
        return [u.toLocalFile() for u in event.mimeData().urls()
                if u.isLocalFile() and u.toLocalFile().lower().endswith(".pdf")]

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and self._pdfs(event):
            event.acceptProposedAction()
            self.setProperty("hover", "true")
            repolish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", "false")
        repolish(self)

    def dropEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", "false")
        repolish(self)
        paths = self._pdfs(event)
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_requested.emit()
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------- toast
class Toast(QFrame):
    """A message that slides in at the bottom of the window and fades away."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Inset")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        self.text = QLabel()
        lay.addWidget(self.text)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text: str, duration_ms: int = 2600) -> None:
        self.text.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 28)
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setDuration(theme.ENTER_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(duration_ms)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setDuration(theme.EXIT_MS)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._hide_when_done)
        self._anim.start()

    def _hide_when_done(self) -> None:
        try:
            self._anim.finished.disconnect(self._hide_when_done)
        except (RuntimeError, TypeError):
            pass
        if self._effect.opacity() < 0.05:
            self.hide()


# ---------------------------------------------------------------- tables
PLATFORM_ROLE = Qt.ItemDataRole.UserRole + 1
PILL_KEYS = ("EBAY", "TIKTOK", "INPOST")


def pill_color(key: str) -> QColor:
    if key in PILL_KEYS:
        return theme.platform_color(key)
    if key == "PENDING":
        return theme.color("warn")
    return theme.color("faint")


class PlatformDelegate(QStyledItemDelegate):
    """Paints a coloured dot and the platform name for the key stored in ``PLATFORM_ROLE``."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        base = pill_color(index.data(PLATFORM_ROLE) or "")
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(base)
        painter.drawEllipse(QPointF(opt.rect.left() + 16, opt.rect.center().y()), 4, 4)
        painter.setPen(theme.color("text"))
        painter.drawText(QRectF(opt.rect.left() + 30, opt.rect.top(), opt.rect.width() - 34, opt.rect.height()),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(140, 36)
