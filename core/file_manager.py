"""File selection helpers, output naming, disk checks and safe deletion of originals."""
from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

from core import config

log = logging.getLogger(__name__)

OUTPUT_KINDS = ("EBAY", "TIKTOK", "INPOST", "PRINTS")


def natural_key(name: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def normalize_selection(paths: Iterable) -> list[Path]:
    """Keep only existing PDFs, drop duplicates, keep the given order."""
    seen: set[str] = set()
    out: list[Path] = []
    for raw in paths:
        p = Path(raw)
        key = os.path.normcase(str(p.resolve()))
        if p.suffix.lower() != ".pdf" or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def download_time(path: Path) -> datetime:
    """Best available 'when was this downloaded' timestamp (creation time on Windows)."""
    st = path.stat()
    stamp = st.st_ctime if sys.platform.startswith("win") else min(st.st_ctime, st.st_mtime)
    return datetime.fromtimestamp(stamp)


def order_by_download_time(paths: list[Path]) -> list[Path]:
    def key(p: Path):
        try:
            return (download_time(p), natural_key(p.name))
        except OSError:
            return (datetime.max, natural_key(p.name))
    return sorted(paths, key=key)


def order_by_name(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: natural_key(p.name))


def default_output_dir(first_input: Path) -> Path:
    return Path(first_input).resolve().parent


def date_string(today: Optional[date] = None) -> str:
    return (today or date.today()).strftime("%Y-%m-%d")


def unique_output_names(out_dir: Path, date_str: str) -> dict[str, Path]:
    """YYYY-MM-DD_EBAY.pdf etc. If any exists already, add _2, _3 ... to all of them (never overwrite)."""
    for n in range(1, 1000):
        suffix = "" if n == 1 else f"_{n}"
        names = {k: Path(out_dir) / f"{date_str}_{k}{suffix}.pdf" for k in OUTPUT_KINDS}
        if not any(p.exists() for p in names.values()):
            return names
    raise RuntimeError("Could not find a free output file name")


def check_output_dir(out_dir: Path) -> None:
    """Raise OSError if the folder cannot be created or written to."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    probe = out_dir / f".write_test_{os.getpid()}.tmp"
    try:
        probe.write_bytes(b"x")
    finally:
        try:
            probe.unlink()
        except OSError:
            pass


def check_disk_space(out_dir: Path, needed_bytes: int) -> None:
    free = shutil.disk_usage(out_dir).free
    if free < needed_bytes + config.DISK_SPACE_SAFETY_BYTES:
        raise OSError(f"Not enough disk space: about {needed_bytes / 1e6:.0f} MB needed, "
                      f"{free / 1e6:.0f} MB free")


def open_folder(path: Path) -> None:
    """Open a folder in the system file browser."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.spawnlp(os.P_NOWAIT, "open", "open", str(path))
        else:
            os.spawnlp(os.P_NOWAIT, "xdg-open", "xdg-open", str(path))
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not open folder %s: %s", path, exc)


@dataclass
class DeletionResult:
    asked: bool = False
    confirmed: bool = False
    deleted: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    message: str = ""


def request_deletion(candidates: list[Path], outputs_verified: bool,
                     confirm_fn: Callable[[list[Path]], bool],
                     outputs: Optional[Iterable[Path]] = None) -> DeletionResult:
    """Ask ONCE whether to delete the originals; delete only the listed files.

    Nothing is deleted unless the outputs were verified, the user confirms, and
    the file is one of ``candidates`` (never an output file, never anything else).
    """
    res = DeletionResult()
    if not outputs_verified:
        res.message = "Outputs not verified - all original files were kept."
        return res
    protected = {os.path.normcase(str(Path(p).resolve())) for p in (outputs or [])}
    files = [Path(p) for p in candidates
             if Path(p).suffix.lower() == ".pdf" and os.path.normcase(str(Path(p).resolve())) not in protected]
    if not files:
        res.message = "No original files to delete."
        return res
    res.asked = True
    res.confirmed = bool(confirm_fn(files))
    if not res.confirmed:
        res.message = "Original files were kept."
        return res
    for p in files:
        try:
            p.unlink()
            res.deleted.append(p)
        except Exception as exc:  # noqa: BLE001
            res.failed.append((p, str(exc)))
            log.error("Could not delete %s: %s", p, exc)
    res.message = f"Deleted {len(res.deleted)} file(s)" + (f"; {len(res.failed)} could not be deleted." if res.failed else ".")
    return res
