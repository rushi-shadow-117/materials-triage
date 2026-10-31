"""Materials Project identifiers.

The REST API returns IDs as a base-26 "AlphaID" (for example mp-aaaaaayt); the official
client formats values below a cut point as the legacy mp-<int> form (mp-643). The encoding
is defined in emmet.core.mpid; this module uses it and nothing else, so the decode is a pure
function with no network.
"""

from __future__ import annotations

import re

from emmet.core.mpid import AlphaID

_ALPHA = re.compile(r"^(?P<prefix>[a-z]+)-(?P<ident>[a-z]+)$")
_LEGACY = re.compile(r"^(?P<prefix>[a-z]+)-(?P<num>\d+)$")


def to_legacy(raw_id: str) -> str:
    """mp-aaaaaayt -> mp-643. Legacy input passes through; unknown shapes raise."""
    if _LEGACY.match(raw_id):
        return raw_id
    m = _ALPHA.match(raw_id)
    if not m:
        raise ValueError(f"not a Materials Project id: {raw_id!r}")
    alpha = AlphaID(m.group("ident"), prefix=m.group("prefix"))
    return str(alpha.formatted)


def to_alpha(legacy_id: str, padlen: int = 8) -> str:
    """mp-643 -> mp-aaaaaayt (padded to the width the API uses)."""
    m = _LEGACY.match(legacy_id)
    if not m:
        raise ValueError(f"not a legacy Materials Project id: {legacy_id!r}")
    return str(AlphaID(int(m.group("num")), padlen=padlen, prefix=m.group("prefix")))
