"""Platform registry. To add a platform: add a module here, a member to ``models.Platform``
(and its one-letter code), and list its SPEC below."""
from __future__ import annotations

from core.models import Platform
from core.platforms import ebay, inpost, tiktok
from core.platforms.base import PlatformSpec

SPECS: tuple[PlatformSpec, ...] = (ebay.SPEC, tiktok.SPEC, inpost.SPEC)
ORDER: tuple[Platform, ...] = tuple(s.platform for s in SPECS)


def count_hits(text: str) -> dict[Platform, int]:
    """How many times each platform is named in ``text`` (zero entries included)."""
    return {spec.platform: spec.count(text) for spec in SPECS}
