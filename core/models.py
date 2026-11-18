"""Plain data structures shared by every module (no PDF or GUI code here)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 (PyMuPDF page coordinates)


class Platform(str, Enum):
    """A marketplace / carrier whose labels get their own output PDF."""

    EBAY = "eBay"
    TIKTOK = "TikTok"
    INPOST = "InPost"

    @property
    def key(self) -> str:
        """Upper-case key used in output file names (``YYYY-MM-DD_<KEY>.pdf``)."""
        return self.name

    @property
    def code(self) -> str:
        """One-letter answer code used by ``AnalysisHooks.ask_platform``."""
        return _CODES[self]

    @classmethod
    def from_code(cls, code: object) -> Optional["Platform"]:
        letter = str(code or "").strip().upper()
        for platform, value in _CODES.items():
            if value == letter:
                return platform
        return None


_CODES = {Platform.EBAY: "E", Platform.TIKTOK: "T", Platform.INPOST: "I"}
SKIP_CODE = "S"


class Status(str, Enum):
    CLASSIFIED = "classified"
    UNRECOGNIZED = "unrecognized"
    SKIPPED = "skipped"


class FlagKind(str, Enum):
    NON_STANDARD_SIZE = "Non-standard page size"
    MULTI_LABEL = "Multi-label page"
    MULTI_UNSPLIT = "Multi-label page NOT separated"
    UNRECOGNIZED = "Unrecognized label"
    SKIPPED = "Skipped by user"
    DUPLICATE = "Duplicate label"
    ANALYSIS_ERROR = "Analysis error"


@dataclass(frozen=True)
class Flag:
    kind: FlagKind
    reason: str
    needs_review: bool


@dataclass
class LabelInfo:
    """One shipping label. ``rect`` is None when the label is the whole page."""

    index: int
    rect: Optional[Box]
    out_size: tuple[float, float]
    platform: Optional[Platform] = None
    status: Status = Status.UNRECOGNIZED
    method: str = ""          # "text", "ocr" or "manual"
    detail: str = ""          # why it is unresolved
    duplicate_of: str = ""
    evidence: str = ""        # why it was classified, e.g. "found 'InPost' (1x)"

    def set_platform(self, platform: Platform, method: str = "manual", evidence: str = "") -> None:
        self.platform = platform
        self.status = Status.CLASSIFIED
        self.method = method
        self.evidence = evidence

    def skip(self) -> None:
        self.platform = None
        self.status = Status.SKIPPED
        self.method = "manual"


@dataclass
class PageInfo:
    file_index: int
    path: Path
    page_number: int           # 1-based page number in the original PDF
    width: float
    height: float
    rotation: int
    size_class: str            # "4x6", "A4" or "other"
    labels: list[LabelInfo] = field(default_factory=list)
    prints_page: int = 0       # 1-based page number inside the PRINTS PDF
    static_flags: list[Flag] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return self.path.name

    def flags(self) -> list[Flag]:
        """All flags for this page, derived from its current state."""
        flags = list(self.static_flags)
        total = len(self.labels)
        for lab in self.labels:
            prefix = f"Label {lab.index + 1} of {total}: " if total > 1 else ""
            if lab.status is Status.UNRECOGNIZED:
                flags.append(Flag(FlagKind.UNRECOGNIZED, prefix + (lab.detail or "platform not recognized"), True))
            elif lab.status is Status.SKIPPED:
                flags.append(Flag(FlagKind.SKIPPED, prefix + "skipped - not included in the eBay/TikTok PDFs", True))
            if lab.duplicate_of:
                flags.append(Flag(FlagKind.DUPLICATE, f"{prefix}duplicate of {lab.duplicate_of}", False))
        return flags

    @property
    def needs_review(self) -> bool:
        return any(f.needs_review for f in self.flags())


@dataclass
class FileInfo:
    path: Path
    page_count: int = 0
    ok: bool = True


@dataclass
class FileIssue:
    path: Path
    reason: str


@dataclass
class ExceptionRow:
    filename: str
    page_number: int
    prints_page: int
    kinds: str
    reason: str
    needs_review: bool


@dataclass
class Stats:
    files_selected: int = 0
    files_readable: int = 0
    file_issues: int = 0
    pages: int = 0
    ebay_labels: int = 0
    tiktok_labels: int = 0
    inpost_labels: int = 0
    unrecognized_pages: int = 0
    skipped_labels: int = 0
    standard_pages: int = 0
    a4_pages: int = 0
    other_size_pages: int = 0
    multi_label_pages: int = 0
    review_pages: int = 0
    duplicate_labels: int = 0


@dataclass
class AskContext:
    filename: str
    page_number: int
    label_number: int
    label_total: int
    reason: str
    excerpt: str
    ambiguous: bool = False                      # True when the text named more than one platform
    candidates: tuple[Platform, ...] = ()        # the platforms the text named (empty = none found)


@dataclass
class Progress:
    stage: str
    filename: str = ""
    file_no: int = 0
    file_total: int = 0
    page_no: int = 0
    page_total: int = 0
    done: int = 0
    total: int = 0


@dataclass
class AnalysisResult:
    inputs: list[Path]
    files: list[FileInfo] = field(default_factory=list)
    pages: list[PageInfo] = field(default_factory=list)
    issues: list[FileIssue] = field(default_factory=list)

    def assign_prints_pages(self) -> None:
        for number, page in enumerate(self.pages, start=1):
            page.prints_page = number

    @property
    def good_files(self) -> list[FileInfo]:
        return [f for f in self.files if f.ok]

    def labels_for(self, platform: Platform) -> list[tuple[PageInfo, LabelInfo]]:
        return [(p, lab) for p in self.pages for lab in p.labels
                if lab.status is Status.CLASSIFIED and lab.platform is platform]

    def pending_labels(self) -> list[tuple[PageInfo, LabelInfo]]:
        return [(p, lab) for p in self.pages for lab in p.labels if lab.status is Status.UNRECOGNIZED]

    def stats(self) -> Stats:
        s = Stats(files_selected=len(self.files), files_readable=len(self.good_files),
                  file_issues=len(self.issues), pages=len(self.pages))
        for page in self.pages:
            if page.size_class == "4x6":
                s.standard_pages += 1
            elif page.size_class == "A4":
                s.a4_pages += 1
            else:
                s.other_size_pages += 1
            kinds = {f.kind for f in page.flags()}
            if len(page.labels) >= 2 or kinds & {FlagKind.MULTI_LABEL, FlagKind.MULTI_UNSPLIT}:
                s.multi_label_pages += 1
            if page.needs_review:
                s.review_pages += 1
            if any(lab.status is not Status.CLASSIFIED for lab in page.labels):
                s.unrecognized_pages += 1
            for lab in page.labels:
                if lab.status is Status.CLASSIFIED and lab.platform is Platform.EBAY:
                    s.ebay_labels += 1
                elif lab.status is Status.CLASSIFIED and lab.platform is Platform.TIKTOK:
                    s.tiktok_labels += 1
                elif lab.status is Status.CLASSIFIED and lab.platform is Platform.INPOST:
                    s.inpost_labels += 1
                elif lab.status is Status.SKIPPED:
                    s.skipped_labels += 1
                if lab.duplicate_of:
                    s.duplicate_labels += 1
        return s

    def exception_rows(self) -> list[ExceptionRow]:
        rows: list[ExceptionRow] = []
        for page in self.pages:
            flags = page.flags()
            if not flags:
                continue
            rows.append(ExceptionRow(
                filename=page.filename, page_number=page.page_number, prints_page=page.prints_page,
                kinds=", ".join(dict.fromkeys(f.kind.value for f in flags)),
                reason="; ".join(f.reason for f in flags),
                needs_review=any(f.needs_review for f in flags)))
        return rows
