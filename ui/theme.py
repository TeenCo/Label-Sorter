"""Dark violet theme: one palette, one stylesheet, a few helpers.

Colours are OKLCH-derived (cool neutrals at hue 290, one soft violet accent at hue 295); the hex
values below are those OKLCH colours converted to sRGB. Depth comes from surface lightness, not
from borders: each layer is a little lighter than the one behind it. Platforms keep their own
colour everywhere they appear (eBay blue, TikTok pink, InPost yellow).
"""
from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication

PALETTE = {
    "bg": "#0E0E13",            # oklch(0.165 0.012 290)  window
    "sidebar": "#08070D",       # oklch(0.135 0.012 290)  recessed rail
    "surface": "#17161D",       # oklch(0.205 0.014 290)  cards
    "raised": "#201F28",        # oklch(0.245 0.016 290)  inputs, buttons
    "hover": "#2A2933",         # oklch(0.285 0.018 290)
    "border": "#35343F",        # oklch(0.33 0.02 290)    only used for focus and drawn controls
    "border_soft": "#24232B",   # oklch(0.26 0.016 290)
    "text": "#EEEEF4",          # oklch(0.95 0.008 290)
    "muted": "#A4A3AE",         # oklch(0.72 0.016 290)
    "faint": "#6E6D7A",         # oklch(0.54 0.02 290)
    "accent": "#B198F7",        # oklch(0.74 0.135 295)   soft violet
    "accent_hover": "#C3AEFF",  # oklch(0.80 0.12 295)
    "accent_ink": "#18102A",    # oklch(0.20 0.05 295)    text on accent
    "preview": "#07070B",       # oklch(0.13 0.01 290)
    "ok": "#67D283",
    "warn": "#F3B94C",
    "danger": "#FA6863",
    "EBAY": "#4C9AFF",
    "TIKTOK": "#FF4D79",
    "INPOST": "#FFC933",
}

# Motion (milliseconds). Entrances ease out; moves inside the window ease in-out; exits are
# about 20% shorter than entrances; list items stagger by 30 ms.
ENTER_MS = 200
EXIT_MS = 160
MOVE_MS = 220
STAGGER_MS = 30
PRESS_SCALE = 0.97

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
#Sidebar { background: $sidebar; }

QLabel { background: transparent; }
QLabel#Title { font-size: 22px; font-weight: 600; }
QLabel#Subtitle { color: $muted; font-size: 13px; }
QLabel#Muted { color: $muted; }
QLabel#Faint { color: $faint; font-size: 12px; }
QLabel#CardTitle { font-size: 14px; font-weight: 600; }
QLabel#BigNumber { font-size: 26px; font-weight: 600; }
QLabel#Brand { font-size: 15px; font-weight: 600; }

QFrame#Card { background: $surface; border: none; border-radius: 14px; }
QFrame#Card[state="attention"] { background: $warn_bg; }
QFrame#Inset { background: $raised; border: none; border-radius: 10px; }
QFrame#Banner { background: $warn_bg; border: none; border-radius: 12px; }
QFrame#Banner[kind="danger"] { background: $danger_bg; }
QFrame#Banner[kind="ok"] { background: $ok_bg; }
QFrame#Banner[kind="info"] { background: $accent_bg; }
QFrame#Preview { background: $preview; border: none; border-radius: 14px; }
QFrame#Preview[state="attention"] { background: $warn_bg; }
QFrame#DropZone { background: $surface; border: none; border-radius: 14px; }
QFrame#DropZone[hover="true"] { background: $accent_bg; }
QFrame#Divider { background: $border_soft; max-height: 1px; min-height: 1px; border: none; }

QPushButton {
    background: $raised; border: 1px solid transparent; border-radius: 8px;
    padding: 8px 14px; color: $text; font-weight: 500;
}
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $surface; }
QPushButton:focus { border-color: $accent; }
QPushButton:disabled { color: $faint; background: $surface; }
QPushButton[variant="primary"] { background: $accent; color: $accent_ink; font-weight: 600; padding: 9px 18px; }
QPushButton[variant="primary"]:hover { background: $accent_hover; }
QPushButton[variant="primary"]:pressed { background: $accent; }
QPushButton[variant="primary"]:disabled { background: $raised; color: $faint; }
QPushButton[variant="ghost"] { background: transparent; color: $muted; }
QPushButton[variant="ghost"]:hover { background: $hover; color: $text; }
QPushButton[variant="danger"] { background: $danger_bg; color: $danger; }
QPushButton[variant="danger"]:hover { background: $danger_hover; }
QPushButton[chip="true"] { background: transparent; border-radius: 8px; padding: 6px 12px; color: $muted; }
QPushButton[chip="true"]:hover { color: $text; background: $raised; }
QPushButton[chip="true"]:checked { background: $hover; color: $text; }
QPushButton[platform="EBAY"] { background: $ebay_bg; }
QPushButton[platform="TIKTOK"] { background: $tiktok_bg; }
QPushButton[platform="INPOST"] { background: $inpost_bg; }
QPushButton[platform="EBAY"]:hover { background: $ebay_hover; }
QPushButton[platform="TIKTOK"]:hover { background: $tiktok_hover; }
QPushButton[platform="INPOST"]:hover { background: $inpost_hover; }
QPushButton[suggested="true"] { border-color: $muted; }
QPushButton[big="true"] { padding: 14px 16px; font-size: 14px; font-weight: 600; border-radius: 10px; text-align: left; }

QTableWidget, QTableView {
    background: transparent; border: none; outline: none; gridline-color: transparent;
    selection-background-color: $accent_sel; selection-color: $text;
}
QTableWidget::item { padding: 6px 10px; border: none; border-radius: 6px; }
QTableWidget::item:hover { background: $raised; }
QTableWidget::item:selected { background: $accent_sel; color: $text; }
QHeaderView { background: transparent; }
QHeaderView::section {
    background: transparent; color: $faint; border: none;
    padding: 8px 10px; font-weight: 500; text-align: left;
}
QTableCornerButton::section { background: transparent; border: none; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $hover; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $faint; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $hover; border-radius: 3px; min-width: 28px; }
QScrollBar::handle:horizontal:hover { background: $faint; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QProgressBar { background: $raised; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; text-align: center; color: transparent; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
QProgressBar[state="attention"]::chunk { background: $warn; }
QProgressBar[state="ok"]::chunk { background: $ok; }

QLineEdit { background: $raised; border: 1px solid transparent; border-radius: 8px; padding: 8px 10px; selection-background-color: $accent; selection-color: $accent_ink; }
QLineEdit:focus { border-color: $accent; }
QLineEdit:read-only { color: $muted; }

QCheckBox { spacing: 8px; color: $muted; }
QCheckBox:hover { color: $text; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; background: $hover; }
QCheckBox::indicator:checked { background: $accent; image: none; }

QPlainTextEdit, QTextEdit { background: $raised; border: none; border-radius: 8px; padding: 6px; color: $muted; }
QListWidget { background: $raised; border: none; border-radius: 8px; padding: 4px; outline: none; }
QListWidget::item { padding: 5px 8px; border-radius: 5px; }

QMenu { background: $raised; border: none; border-radius: 10px; padding: 5px; }
QMenu::item { padding: 7px 22px 7px 14px; border-radius: 6px; }
QMenu::item:selected { background: $hover; }
QMenu::separator { height: 1px; background: $border_soft; margin: 4px 8px; }
QToolTip { background: $raised; color: $text; border: none; padding: 5px 8px; border-radius: 6px; }
""")


def stylesheet() -> str:
    values = dict(PALETTE)
    tint, strong = 0.12, 0.20             # the only two opacities used for tinted fills
    values.update(
        warn_bg=rgba("warn", tint),
        danger_bg=rgba("danger", tint), danger_hover=rgba("danger", strong),
        ok_bg=rgba("ok", tint),
        accent_bg=rgba("accent", tint), accent_sel=rgba("accent", strong),
        ebay_bg=rgba("EBAY", tint), ebay_hover=rgba("EBAY", strong),
        tiktok_bg=rgba("TIKTOK", tint), tiktok_hover=rgba("TIKTOK", strong),
        inpost_bg=rgba("INPOST", tint), inpost_hover=rgba("INPOST", strong),
    )
    return _QSS.substitute(values)


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")                      # consistent base on every OS; the QSS does the rest
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSizeF(9.5)
    app.setFont(font)
    app.setStyleSheet(stylesheet())
