"""Dark theme: one palette, one stylesheet, a few helpers.

Look and feel follows the dark developer tools people already know (GitHub / Linear):
quiet blue-grey surfaces, hairline borders, one indigo accent, and each platform keeps
its own colour (eBay blue, TikTok pink, InPost yellow) everywhere it appears.
"""
from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication

PALETTE = {
    "bg": "#0D1117",          # window
    "sidebar": "#090C11",
    "surface": "#151B23",     # cards
    "raised": "#1B232D",      # inputs, table headers
    "hover": "#222C38",
    "border": "#2A3441",
    "border_soft": "#1E2733",
    "text": "#E6EDF3",
    "muted": "#8D99A8",
    "faint": "#5C6878",
    "accent": "#7C8CFF",
    "accent_hover": "#95A2FF",
    "accent_ink": "#0A0F24",  # text on accent
    "ok": "#3FB950",
    "warn": "#E3A008",
    "danger": "#F85149",
    "EBAY": "#4C9AFF",
    "TIKTOK": "#FF4D79",
    "INPOST": "#FFC933",
}

FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue", "Arial"]


def color(name: str) -> QColor:
    return QColor(PALETTE[name])


def rgba(name: str, alpha: float) -> str:
    """CSS colour with an integer 0-255 alpha (the form Qt style sheets parse reliably)."""
    c = QColor(PALETTE.get(name, name))
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {round(alpha * 255)})"


def platform_color(key: str) -> QColor:
    """Colour for a platform key (``EBAY`` / ``TIKTOK`` / ``INPOST``)."""
    return QColor(PALETTE.get(key, PALETTE["muted"]))


_QSS = Template("""
QWidget { background: transparent; color: $text; font-size: 13px; }
QMainWindow, QDialog { background: $bg; }
#Root, #Content { background: $bg; }
#Sidebar { background: $sidebar; border-right: 1px solid $border_soft; }

QLabel { background: transparent; }
QLabel#Title { font-size: 22px; font-weight: 600; }
QLabel#Subtitle { color: $muted; font-size: 13px; }
QLabel#Muted { color: $muted; }
QLabel#Faint { color: $faint; font-size: 12px; }
QLabel#CardTitle { font-size: 14px; font-weight: 600; }
QLabel#BigNumber { font-size: 26px; font-weight: 600; }
QLabel#Brand { font-size: 15px; font-weight: 600; }

QFrame#Card { background: $surface; border: 1px solid $border_soft; border-radius: 12px; }
QFrame#Card[state="attention"] { border: 1px solid $warn; }
QFrame#Inset { background: $raised; border: 1px solid $border_soft; border-radius: 8px; }
QFrame#Banner { background: $warn_bg; border: 1px solid $warn_line; border-radius: 10px; }
QFrame#Banner[kind="danger"] { background: $danger_bg; border: 1px solid $danger_line; }
QFrame#Banner[kind="ok"] { background: $ok_bg; border: 1px solid $ok_line; }
QFrame#Banner[kind="info"] { background: $accent_bg; border: 1px solid $accent_line; }
QFrame#Preview { background: #0A0D12; border: 1px solid $border_soft; border-radius: 12px; }
QFrame#Preview[state="attention"] { border: 1px solid $warn; }
QFrame#DropZone { background: $surface; border: 1px dashed $border; border-radius: 12px; }
QFrame#DropZone[hover="true"] { background: $accent_bg; border: 1px dashed $accent; }
QFrame#Divider { background: $border_soft; max-height: 1px; min-height: 1px; border: none; }

QPushButton {
    background: $raised; border: 1px solid $border; border-radius: 8px;
    padding: 7px 14px; color: $text; font-weight: 500;
}
QPushButton:hover { background: $hover; border-color: $faint; }
QPushButton:pressed { background: $surface; }
QPushButton:focus { border-color: $accent; }
QPushButton:disabled { color: $faint; background: $surface; border-color: $border_soft; }
QPushButton[variant="primary"] { background: $accent; border: 1px solid $accent; color: $accent_ink; font-weight: 600; padding: 8px 18px; }
QPushButton[variant="primary"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton[variant="primary"]:pressed { background: $accent; }
QPushButton[variant="primary"]:disabled { background: $raised; border-color: $border_soft; color: $faint; }
QPushButton[variant="ghost"] { background: transparent; border: 1px solid transparent; color: $muted; }
QPushButton[variant="ghost"]:hover { background: $hover; color: $text; }
QPushButton[variant="danger"] { background: $danger_bg; border: 1px solid $danger_line; color: $danger; }
QPushButton[variant="danger"]:hover { background: $danger_hover; }
QPushButton[chip="true"] { background: transparent; border: 1px solid $border; border-radius: 14px; padding: 4px 12px; color: $muted; }
QPushButton[chip="true"]:hover { color: $text; border-color: $faint; }
QPushButton[chip="true"]:checked { background: $accent_bg; border-color: $accent; color: $text; }
QPushButton[platform="EBAY"] { border: 1px solid $ebay_line; }
QPushButton[platform="TIKTOK"] { border: 1px solid $tiktok_line; }
QPushButton[platform="INPOST"] { border: 1px solid $inpost_line; }
QPushButton[platform="EBAY"]:hover { background: $ebay_bg; border-color: $EBAY; }
QPushButton[platform="TIKTOK"]:hover { background: $tiktok_bg; border-color: $TIKTOK; }
QPushButton[platform="INPOST"]:hover { background: $inpost_bg; border-color: $INPOST; }
QPushButton[suggested="true"] { background: $hover; }
QPushButton[big="true"] { padding: 14px 16px; font-size: 14px; font-weight: 600; border-radius: 10px; text-align: left; }

QTableWidget, QTableView {
    background: transparent; border: none; outline: none; gridline-color: transparent;
    selection-background-color: $accent_bg; selection-color: $text;
}
QTableWidget::item { padding: 6px 10px; border: none; border-bottom: 1px solid $border_soft; }
QTableWidget::item:hover { background: $raised; }
QTableWidget::item:selected { background: $accent_sel; color: $text; }
QHeaderView { background: transparent; }
QHeaderView::section {
    background: transparent; color: $muted; border: none; border-bottom: 1px solid $border;
    padding: 8px 10px; font-weight: 500; text-align: left;
}
QTableCornerButton::section { background: transparent; border: none; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $faint; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 3px; min-width: 28px; }
QScrollBar::handle:horizontal:hover { background: $faint; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QProgressBar { background: $raised; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; text-align: center; color: transparent; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
QProgressBar[state="attention"]::chunk { background: $warn; }
QProgressBar[state="ok"]::chunk { background: $ok; }

QLineEdit { background: $raised; border: 1px solid $border; border-radius: 8px; padding: 7px 10px; selection-background-color: $accent; selection-color: $accent_ink; }
QLineEdit:focus { border-color: $accent; }
QLineEdit:read-only { color: $muted; }

QCheckBox { spacing: 8px; color: $muted; }
QCheckBox:hover { color: $text; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid $border; background: $raised; }
QCheckBox::indicator:hover { border-color: $faint; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: none; }

QPlainTextEdit, QTextEdit { background: $raised; border: 1px solid $border_soft; border-radius: 8px; padding: 6px; color: $muted; }
QListWidget { background: $raised; border: 1px solid $border_soft; border-radius: 8px; padding: 4px; outline: none; }
QListWidget::item { padding: 5px 8px; border-radius: 5px; }

QMenu { background: $surface; border: 1px solid $border; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 22px 7px 14px; border-radius: 5px; }
QMenu::item:selected { background: $hover; }
QMenu::separator { height: 1px; background: $border_soft; margin: 4px 8px; }
QToolTip { background: $raised; color: $text; border: 1px solid $border; padding: 5px 8px; border-radius: 6px; }
""")


def stylesheet() -> str:
    values = dict(PALETTE)
    values.update(
        warn_bg=rgba("warn", 0.10), warn_line=rgba("warn", 0.45),
        danger_bg=rgba("danger", 0.10), danger_line=rgba("danger", 0.45), danger_hover=rgba("danger", 0.20),
        ok_bg=rgba("ok", 0.10), ok_line=rgba("ok", 0.45),
        accent_bg=rgba("accent", 0.12), accent_line=rgba("accent", 0.45), accent_sel=rgba("accent", 0.20),
        ebay_bg=rgba("EBAY", 0.12), ebay_line=rgba("EBAY", 0.45),
        tiktok_bg=rgba("TIKTOK", 0.12), tiktok_line=rgba("TIKTOK", 0.45),
        inpost_bg=rgba("INPOST", 0.12), inpost_line=rgba("INPOST", 0.45),
    )
    return _QSS.substitute(values)


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")                      # consistent base on every OS; the QSS does the rest
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSizeF(9.5)
    app.setFont(font)
    app.setStyleSheet(stylesheet())
