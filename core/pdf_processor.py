"""Generate the PRINTS / EBAY / TIKTOK / INPOST PDFs using native PDF page operations only.

Pages are copied with PyMuPDF's insert_pdf (content streams, fonts, images and
vector barcodes are carried over untouched). Separating labels on a multi-label
page is done by setting the page's CropBox; nothing is rasterized or re-encoded.
"""
from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from core import config
from core import file_manager
from core import validation
from core.models import AnalysisResult, Progress, Status

log = logging.getLogger(__name__)

ProgressFn = Callable[[Progress], None]


@dataclass
class GenerationResult:
    ok: bool = False
    outputs: dict[str, Path] = field(default_factory=dict)
    page_counts: dict[str, int] = field(default_factory=dict)
    report_path: Optional[Path] = None
    csv_path: Optional[Path] = None
    errors: list[str] = field(default_factory=list)
    verified: bool = False


def _save_document(doc, path: Path) -> None:
    """Write a document. garbage=4 only removes unused/duplicate objects; streams are not recompressed."""
    doc.save(str(path), garbage=4, deflate=False)


def expected_sizes(result: AnalysisResult) -> dict[str, list[tuple[float, float]]]:
    sizes: dict[str, list[tuple[float, float]]] = {kind: [] for kind in file_manager.OUTPUT_KINDS}
    for page in result.pages:
        sizes["PRINTS"].append((page.width, page.height))
        for lab in page.labels:
            if lab.status is Status.CLASSIFIED and lab.platform is not None:
                sizes[lab.platform.key].append(lab.out_size)
    return sizes


def generate_outputs(result: AnalysisResult, out_dir: Path, progress: Optional[ProgressFn] = None,
                     date_str: Optional[str] = None) -> GenerationResult:
    """Build, verify and publish the output PDFs. On any failure nothing is left behind."""
    import fitz

    gen = GenerationResult()
    out_dir = Path(out_dir)
    good = result.good_files
    if not good or not result.pages:
        gen.errors.append("There are no readable pages to process.")
        return gen
    pending = result.pending_labels()
    if pending:
        gen.errors.append(f"{len(pending)} label(s) are still unclassified - classify or skip them first.")
        return gen

    try:
        file_manager.check_output_dir(out_dir)
        total_bytes = sum(f.path.stat().st_size for f in good)
        max_labels = max((len(p.labels) for p in result.pages), default=1)
        file_manager.check_disk_space(out_dir, total_bytes * (2 + max_labels))
        names = file_manager.unique_output_names(out_dir, date_str or file_manager.date_string())
    except OSError as exc:
        gen.errors.append(f"Output folder problem: {exc}")
        return gen

    temp_paths: dict[str, Path] = {}
    final_paths: dict[str, Path] = {}
    docs = {kind: fitz.open() for kind in file_manager.OUTPUT_KINDS}
    published: list[Path] = []
    try:
        pages_by_file: dict[int, list] = {}
        for page in result.pages:
            pages_by_file.setdefault(page.file_index, []).append(page)
        total = len(result.pages)
        done = 0
        readable_no = 0
        for file_index, finfo in enumerate(result.files):
            if not finfo.ok:
                continue
            readable_no += 1
            src = fitz.open(str(finfo.path))
            try:
                if src.page_count != finfo.page_count:
                    raise RuntimeError(f"{finfo.path.name} changed during processing "
                                       f"({src.page_count} pages instead of {finfo.page_count})")
                docs["PRINTS"].insert_pdf(src)  # every original page, unmodified, in order
                for page in pages_by_file.get(file_index, []):
                    for lab in page.labels:
                        if lab.status is not Status.CLASSIFIED or lab.platform is None:
                            continue
                        target = docs[lab.platform.key]
                        target.insert_pdf(src, from_page=page.page_number - 1, to_page=page.page_number - 1)
                        if lab.rect is not None:
                            target.load_page(target.page_count - 1).set_cropbox(fitz.Rect(*lab.rect))
                    done += 1
                    if progress:
                        progress(Progress("Generating", finfo.path.name, readable_no, len(good),
                                          page.page_number, finfo.page_count, done, total))
            finally:
                src.close()

        sizes = expected_sizes(result)
        for kind, doc in docs.items():
            if doc.page_count == 0:
                continue
            final_paths[kind] = names[kind]
            temp_paths[kind] = names[kind].with_name(names[kind].name + ".part")
            _save_document(doc, temp_paths[kind])
            gen.page_counts[kind] = doc.page_count
        for doc in docs.values():
            doc.close()
        docs = {}

        problems: list[str] = []
        for kind, tmp in temp_paths.items():
            problems += validation.verify_pdf(tmp, sizes[kind])
        if problems:
            gen.errors.extend(problems)
            raise RuntimeError("Verification of the generated PDFs failed")

        for kind, tmp in temp_paths.items():
            os.replace(tmp, final_paths[kind])
            published.append(final_paths[kind])
        temp_paths.clear()
        gen.outputs = dict(final_paths)
        gen.verified = True
        gen.ok = True
    except Exception as exc:  # noqa: BLE001
        log.exception("Output generation failed")
        if str(exc) not in gen.errors:
            gen.errors.append(str(exc))
        for tmp in temp_paths.values():
            _silent_remove(tmp)
        for path in published:
            _silent_remove(path)
        gen.outputs.clear()
        gen.page_counts.clear()
        gen.ok = False
        gen.verified = False
    finally:
        for doc in docs.values():
            try:
                doc.close()
            except Exception:  # noqa: BLE001
                pass

    if gen.ok:
        try:
            write_reports(result, gen, out_dir, names["PRINTS"].stem.replace("_PRINTS", ""))
        except OSError as exc:
            gen.errors.append(f"Reports could not be written: {exc}")
    return gen


def _silent_remove(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass


def write_exceptions_csv(path: Path, rows) -> None:
    """Write the flagged-pages list (also used by the 'Export list' button)."""
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Filename", "Original page", "PRINTS PDF page", "Kind", "Reason", "Needs review"])
        for r in rows:
            writer.writerow([r.filename, r.page_number, r.prints_page, r.kinds, r.reason,
                             "YES" if r.needs_review else "no"])


def write_reports(result: AnalysisResult, gen: GenerationResult, out_dir: Path, stem: str) -> None:
    """Write <stem>_REPORT.txt and <stem>_EXCEPTIONS.csv next to the PDFs."""
    gen.csv_path = out_dir / f"{stem}_EXCEPTIONS.csv"
    gen.report_path = out_dir / f"{stem}_REPORT.txt"
    rows = result.exception_rows()
    write_exceptions_csv(gen.csv_path, rows)
    s = result.stats()
    lines = [f"{config.APP_NAME} - processing report", "=" * 60, "",
             "Original files (in processing order):"]
    for f in result.files:
        lines.append(f"  {f.path.name}  - {f.page_count} page(s)" if f.ok else f"  {f.path.name}  - NOT PROCESSED")
    lines += ["", "Summary:",
              f"  Files selected: {s.files_selected}   readable: {s.files_readable}   problems: {s.file_issues}",
              f"  Original pages: {s.pages}  (4x6: {s.standard_pages}, A4: {s.a4_pages}, other: {s.other_size_pages})",
              f"  eBay labels: {s.ebay_labels}   TikTok labels: {s.tiktok_labels}   InPost labels: {s.inpost_labels}",
              f"  Unclassified/skipped labels: {s.skipped_labels}   Multi-label pages: {s.multi_label_pages}",
              f"  Pages needing manual review: {s.review_pages}", "", "Output files:"]
    for kind in ("PRINTS", "EBAY", "TIKTOK", "INPOST"):
        if kind in gen.outputs:
            lines.append(f"  {gen.outputs[kind].name}  - {gen.page_counts[kind]} page(s)")
    if result.issues:
        lines += ["", "Files that could NOT be processed (kept untouched):"]
        lines += [f"  {i.path.name}: {i.reason}" for i in result.issues]
    lines += ["", "Flagged pages (PRINTS PDF page numbers refer to the PRINTS file):",
              f"  {'File':<32} {'Orig.':>5} {'PRINTS':>6}  Reason"]
    for r in rows:
        lines.append(f"  {r.filename[:32]:<32} {r.page_number:>5} {r.prints_page:>6}  "
                     f"{'[REVIEW] ' if r.needs_review else ''}{r.kinds}: {r.reason}")
    if not rows:
        lines.append("  (none)")
    gen.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
