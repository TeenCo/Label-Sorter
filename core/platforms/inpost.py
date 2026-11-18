"""InPost labels (locker / shop drop-off labels, also those bought through eBay).

Recognised by the brand word 'InPost'. It must be one word and must not be glued to a
preceding letter ('signpost') or followed by one, so ordinary prose such as
'sent in post' is not matched. OCR reads the logo as 'InPost' as well.
"""
import re

from core.models import Platform
from core.platforms.base import PlatformSpec

SPEC = PlatformSpec(Platform.INPOST, (re.compile(r"(?<![a-z0-9])inpost(?![a-z])", re.IGNORECASE),))
