"""Dialogs: the single confirmation for deleting the originals, and plain notices."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QMessageBox, QVBoxLayout, QWidget

from ui.widgets import button, label


class DeleteDialog(QDialog):
    """Lists the originals and asks once. 'Keep files' is the default button."""

    def __init__(self, parent: QWidget, files: list[Path]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Delete original files?")
        self.setModal(True)
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(label("Delete the original PDFs?", "CardTitle"))
        lay.addWidget(label("The sorted files were generated and verified. These originals will be deleted "
                            "permanently:", "Muted", wrap=True))
        box = QListWidget()
        box.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for p in files:
            box.addItem(p.name)
        box.setMinimumHeight(min(max(len(files), 3), 10) * 28 + 12)
        lay.addWidget(box)
        row = QHBoxLayout()
        row.addStretch(1)
        keep = button("Keep files")
        delete = button(f"Delete {len(files)} file{'s' if len(files) != 1 else ''}", "danger")
        keep.clicked.connect(self.reject)
        delete.clicked.connect(self.accept)
        row.addWidget(keep)
        row.addWidget(delete)
        lay.addLayout(row)
        keep.setDefault(True)
        keep.setFocus()


def notice(parent: Optional[QWidget], title: str, text: str, kind: str = "info") -> None:
    icon = {"info": QMessageBox.Icon.Information, "warn": QMessageBox.Icon.Warning,
            "error": QMessageBox.Icon.Critical}.get(kind, QMessageBox.Icon.Information)
    box = QMessageBox(icon, title, text, QMessageBox.StandardButton.Ok, parent)
    box.exec()
