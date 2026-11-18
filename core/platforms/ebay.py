"""eBay labels: the word 'eBay' (not glued to a preceding letter or digit)."""
import re

from core.models import Platform
from core.platforms.base import PlatformSpec

SPEC = PlatformSpec(Platform.EBAY, (re.compile(r"(?<![a-z0-9])ebay", re.IGNORECASE),))
