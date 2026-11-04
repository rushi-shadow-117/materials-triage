"""web/src/help.ts holds every plain-language help entry in one file for owner review. This
test keeps it complete: every criterion, flag, caveat, exclusion rule, evidence tier, and
screen the code can show has an entry, and every entry is marked for review."""

from __future__ import annotations

import re
from pathlib import Path

from materials_triage.api import help as help_mod

HELP_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "help.ts"
SCREENS = {"workspace", "results", "drill", "console", "history", "help"}


def _entries(block_name: str) -> dict[str, str]:
    """The keys of one exported object literal and the text of each entry."""
    text = HELP_TS.read_text()
    m = re.search(rf"export const {block_name}[^=]*=\s*\{{(.*?)\n\}};", text, re.S)
    assert m, f"{block_name} is not exported from help.ts"
    body = m.group(1)
    out: dict[str, str] = {}
    entry = re.compile(r'\n  "?([A-Za-z_.]+)"?:\s*\{\s*text:\s*"((?:[^"\\]|\\.)*)"')
    for key, value in entry.findall(body):
        out[key] = value
    return out


def test_every_vocabulary_key_has_a_help_entry() -> None:
    keys = help_mod.keys()
    criteria = _entries("CRITERION_HELP")
    flags = _entries("FLAG_HELP")
    caveats = _entries("CAVEAT_HELP")
    rules = _entries("EXCLUSION_HELP")
    tiers = _entries("EVIDENCE_TIER_HELP")
    screens = _entries("SCREEN_HELP")
    assert set(keys["criteria"]) <= set(criteria), set(keys["criteria"]) - set(criteria)
    assert set(keys["flags"]) <= set(flags), set(keys["flags"]) - set(flags)
    # a caveat that is also a flag is explained once, as the flag
    assert set(keys["caveats"]) <= set(caveats) | set(flags), (
        set(keys["caveats"]) - set(caveats) - set(flags)
    )
    assert set(keys["exclusion_rules"]) <= set(rules), set(keys["exclusion_rules"]) - set(rules)
    assert set(keys["evidence_tiers"]) <= set(tiers), set(keys["evidence_tiers"]) - set(tiers)
    assert set(screens) >= SCREENS, SCREENS - set(screens)
    for block in (criteria, flags, caveats, rules, tiers, screens):
        for key, text in block.items():
            assert text.strip(), f"{key} has empty help text"


def test_every_entry_is_marked_for_owner_review_and_names_a_source() -> None:
    text = HELP_TS.read_text()
    opened = len(re.findall(r"\{\s*text:\s*\"", text))
    sourced = len(re.findall(r"\n\s*source:\s*\"[^\"]+\",\s*review:\s*\"owner\"", text))
    inline = len(re.findall(r"\",\s*source:\s*\"[^\"]+\",\s*review:\s*\"owner\"\s*\}", text))
    assert opened == sourced + inline, 'every entry is {text, source, review: "owner"}'
