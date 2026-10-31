"""Cross-source polymorph matching: ICSD intersection first, then composition + space group."""

from __future__ import annotations

from dataclasses import dataclass

from materials_triage.records import MatchRule, Polymorph


@dataclass(frozen=True)
class Match:
    left: Polymorph
    right: Polymorph
    rule: MatchRule


def match_polymorphs(left: list[Polymorph], right: list[Polymorph]) -> list[Match]:
    """Pair polymorphs across two sources. Each right item is used at most once."""
    matches: list[Match] = []
    taken: set[int] = set()
    # Pass 1: shared ICSD ids (strongest evidence that two records describe one structure).
    for a in left:
        if not a.ids.icsd:
            continue
        for j, b in enumerate(right):
            if j in taken or not b.ids.icsd:
                continue
            if set(a.ids.icsd) & set(b.ids.icsd):
                matches.append(Match(a, b, MatchRule.ICSD_INTERSECTION))
                taken.add(j)
                break
    matched_left = {id(m.left) for m in matches}
    # Pass 2: same reduced composition and space group number.
    for a in left:
        if id(a) in matched_left or a.spacegroup_number is None:
            continue
        for j, b in enumerate(right):
            if j in taken:
                continue
            if a.composition == b.composition and a.spacegroup_number == b.spacegroup_number:
                matches.append(Match(a, b, MatchRule.COMPOSITION_SPACEGROUP))
                taken.add(j)
                break
    return matches
