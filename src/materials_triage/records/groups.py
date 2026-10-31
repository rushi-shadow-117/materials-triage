"""Join per-source records into one CompositionGroup. Pure; no policy.

Ground state is the lowest mixed-hull polymorph among those not excluded. If it is
theoretical, the flag is set and the lowest observed polymorph is named beside it, so Phase 2
scoring can never silently pick a hypothetical phase.
"""

from __future__ import annotations

from materials_triage.records import (
    CompositionGroup,
    ExperimentalGapAggregate,
    HazardRecord,
    LiteratureSearchResult,
    MatchRule,
    Polymorph,
)
from materials_triage.records.matching import match_polymorphs

MIXED_HULL = "GGA_GGA+U_R2SCAN"


def merge_matches(mp_polys: list[Polymorph], other_polys: list[Polymorph]) -> list[Polymorph]:
    """Attach ids, values, and evidence from matched polymorphs onto the MP polymorphs.
    Unmatched polymorphs from the other source are appended as their own entries."""
    matches = match_polymorphs(mp_polys, other_polys)
    by_left = {id(m.left): m for m in matches}
    matched_right = {id(m.right) for m in matches}
    merged: list[Polymorph] = []
    for p in mp_polys:
        m = by_left.get(id(p))
        if m is None:
            merged.append(p)
            continue
        q = m.right
        merged.append(
            p.model_copy(
                update={
                    "ids": p.ids.model_copy(
                        update={
                            "jarvis_jid": p.ids.jarvis_jid or q.ids.jarvis_jid,
                            "oqmd": p.ids.oqmd or q.ids.oqmd,
                            "cod": sorted(set(p.ids.cod) | set(q.ids.cod)),
                            "icsd": sorted(set(p.ids.icsd) | set(q.ids.icsd)),
                        }
                    ),
                    "hull_energy": {**q.hull_energy, **p.hull_energy},
                    "band_gap": {**q.band_gap, **p.band_gap},
                    "dielectric": {**q.dielectric, **p.dielectric},
                    "observation_evidence": list(
                        dict.fromkeys([*p.observation_evidence, *q.observation_evidence])
                    ),
                    "observed": p.observed
                    or q.observed
                    or (None if p.observed is None and q.observed is None else False),
                    "matched_by": m.rule,
                    "provenance": [*p.provenance, *q.provenance],
                }
            )
        )
    merged.extend(q for q in other_polys if id(q) not in matched_right)
    return merged


def build_group(
    composition: str,
    polymorphs: list[Polymorph],
    *,
    experimental_gaps: ExperimentalGapAggregate | None = None,
    hazard: HazardRecord | None = None,
    literature: LiteratureSearchResult | None = None,
    hull_key: str = MIXED_HULL,
) -> CompositionGroup:
    with_hull = [p for p in polymorphs if p.ids.mp and p.ground_state_energy(hull_key) is not None]
    ground = min(
        with_hull, key=lambda p: (p.ground_state_energy(hull_key), p.ids.mp or ""), default=None
    )
    observed = [p for p in with_hull if p.observed is True]
    lowest_observed = min(
        observed, key=lambda p: (p.ground_state_energy(hull_key), p.ids.mp or ""), default=None
    )
    return CompositionGroup(
        composition=composition,
        polymorphs=polymorphs,
        ground_state_mp=ground.ids.mp if ground else None,
        ground_state_is_theoretical=(None if ground is None else ground.theoretical is True),
        lowest_observed_mp=lowest_observed.ids.mp if lowest_observed else None,
        experimental_gaps=experimental_gaps,
        hazard=hazard,
        literature=literature,
    )


__all__ = ["MatchRule", "build_group", "merge_matches"]
