"""Shape of a platform definition."""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.models import Platform


@dataclass(frozen=True)
class PlatformSpec:
    """How one platform is recognised in label text.

    ``patterns`` run against the text (or OCR output) of a single label. Add
    a pattern here to teach the app another spelling; nothing else needs to change.
    """

    platform: Platform
    patterns: tuple[re.Pattern, ...]

    def count(self, text: str) -> int:
        return sum(len(p.findall(text)) for p in self.patterns)
