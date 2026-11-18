"""TikTok Shop labels: 'TikTok', 'Tik Tok', 'Tik-Tok'."""
import re

from core.models import Platform
from core.platforms.base import PlatformSpec

SPEC = PlatformSpec(Platform.TIKTOK, (re.compile(r"(?<![a-z0-9])tik[\s\-_]?tok", re.IGNORECASE),))
