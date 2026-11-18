"""Entry point:  python main.py"""
from __future__ import annotations

import logging
import logging.handlers
import sys

from core import config


def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if sys.stderr is not None:                      # a windowed .exe has no console
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(fmt)
        root.addHandler(console)
    try:
        fh = logging.handlers.RotatingFileHandler(config.log_directory() / "label_sorter.log",
                                                  maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass


def _missing(package: str) -> int:
    message = f"{package} is not installed. Run:  pip install -r requirements.txt"
    print(message, file=sys.stderr if sys.stderr else sys.stdout)
    return 1


def main() -> int:
    setup_logging()
    try:
        import fitz  # noqa: F401
    except ImportError:
        return _missing("PyMuPDF")
    try:
        import PySide6  # noqa: F401
    except ImportError:
        return _missing("PySide6")
    import ui
    return ui.run()


if __name__ == "__main__":
    sys.exit(main())
