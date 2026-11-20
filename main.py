"""Entry point:  python main.py"""
from __future__ import annotations

import importlib.util
import logging
import logging.handlers
import sys
import threading

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


def _preload_pdf_engine() -> None:
    try:
        import fitz  # noqa: F401  (the slow part of the first analysis: load it while the window builds)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    setup_logging()
    # find_spec only checks that a package exists; it does not import it (importing PySide6 and
    # PyMuPDF here used to happen twice, once for the check and once for real).
    if importlib.util.find_spec("fitz") is None:
        return _missing("PyMuPDF")
    if importlib.util.find_spec("PySide6") is None:
        return _missing("PySide6")
    threading.Thread(target=_preload_pdf_engine, name="preload-pdf", daemon=True).start()
    import ui
    return ui.run()


if __name__ == "__main__":
    sys.exit(main())
