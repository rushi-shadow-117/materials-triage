"""In-app help (Track H item 2): the two role guides served read-only from docs/, and the
closed vocabularies the web app's help text must cover.

The guide route maps a fixed name to a fixed file; no request value reaches the filesystem.
`keys()` is what `tests/test_help_text.py` checks `web/src/help.ts` against, so a new flag,
caveat, criterion, exclusion rule, or evidence label cannot ship without a plain-language
entry.
"""

from __future__ import annotations

from pathlib import Path

from materials_triage.config.schema import CRITERIA, CoreConfig
from materials_triage.records.bundle import CaveatId, ExclusionRule, Flag

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"
GUIDES: dict[str, str] = {
    "scientist": "SCIENTIST_GUIDE.md",
    "admin": "ADMIN_GUIDE.md",
}


def guide_text(name: str) -> str | None:
    """The guide's Markdown, or None for a name that is not a guide."""
    file = GUIDES.get(name)
    if file is None:
        return None
    return (DOCS / file).read_text(encoding="utf-8")


def keys() -> dict[str, list[str]]:
    return {
        "criteria": list(CRITERIA),
        "flags": [f.value for f in Flag],
        "caveats": [c.value for c in CaveatId],
        "exclusion_rules": [r.value for r in ExclusionRule],
        "evidence_tiers": list(CoreConfig().evidence_labels),
        "guides": list(GUIDES),
    }
