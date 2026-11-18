"""Qt user interface (PySide6). The engine in ``core`` never imports from here."""
from __future__ import annotations

import sys


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from core import config
    from ui import theme
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    theme.apply(app)
    window = MainWindow()
    window.show()
    return app.exec()
