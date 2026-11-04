"""Polymorph selection and the per-composition summary the bundle carries.

The scorer scores one polymorph per composition: the ground state (lowest mixed-hull energy
among MP polymorphs not excluded by license or deprecation) unless the PI named an MP id.
`summarize_group` reduces a full `CompositionGroup` to the `CompositionSummary` the bundle
carries; the full list stays in the provenance store under `composition_id`. Counts cover
the MP-identified polymorphs (the store's `mp_summary` records); unmatched JARVIS entries
contribute values through matching, never rows of their own.
"""

from __future__ import annotations

from materials_triage.records import CompositionGroup, Polymorph, ReferenceValue
from materials_triage.records.bundle import (
    CompositionSummary,
    ExclusionRule,
    PolymorphSummary,
    PolymorphSummaryRow,
)

MIXED_HULL = "GGA_GGA+U_R2SCAN"
TOP_N = 5


def _hull_mev(p: Polymorph, hull_key: str) -> float | None:
    v = p.ground_state_energy(hull_key)
    return None if v is None else v * 1000.0


def polymorph_exclusion(
    p: Polymorph, *, cutoff_mev: float | None, hull_key: str = MIXED_HULL
) -> ExclusionRule | None:
    """Adapter rules first (license, deprecated), then the stability cutoff."""
    if p.deprecated:
        return ExclusionRule.DEPRECATED
    if p.license == "BY-NC":
        return ExclusionRule.LICENSE_NON_COMMERCIAL
    hull = _hull_mev(p, hull_key)
    if cutoff_mev is not None and hull is not None and hull > cutoff_mev:
        return ExclusionRule.STABILITY_CUTOFF
    return None


def _sort_key(p: Polymorph, hull_key: str) -> tuple[float, str]:
    hull = _hull_mev(p, hull_key)
    return (float("inf") if hull is None else hull, p.ids.mp or "")


def mp_polymorphs(group: CompositionGroup, hull_key: str = MIXED_HULL) -> list[Polymorph]:
    """MP-identified polymorphs, lowest hull first, ties by MP id."""
    return sorted((p for p in group.polymorphs if p.ids.mp), key=lambda p: _sort_key(p, hull_key))


def select_scored(
    group: CompositionGroup, *, requested_mp: str | None = None, hull_key: str = MIXED_HULL
) -> Polymorph | None:
    """The polymorph to score: the requested MP id when given (whatever its hull energy, so
    the stability rule can exclude it visibly), else the ground state among polymorphs not
    excluded by an adapter rule."""
    polys = mp_polymorphs(group, hull_key)
    if requested_mp is not None:
        return next((p for p in polys if p.ids.mp == requested_mp), None)
    for p in polys:
        if polymorph_exclusion(p, cutoff_mev=None) is None and _hull_mev(p, hull_key) is not None:
            return p
    return None


def summary_row(
    p: Polymorph, *, cutoff_mev: float | None, hull_key: str = MIXED_HULL
) -> PolymorphSummaryRow:
    return PolymorphSummaryRow(
        mp_id=p.ids.mp,
        jarvis_jid=p.ids.jarvis_jid,
        spacegroup_number=p.spacegroup_number,
        spacegroup_symbol=p.spacegroup_symbol,
        hull_energy=p.hull_energy.get(hull_key),
        is_stable=dict(p.is_stable),
        hull_status_conflict=p.hull_status_conflict,
        observed=p.observed,
        theoretical=p.theoretical,
        band_gap=dict(p.band_gap),
        dielectric=dict(p.dielectric),
        excluded_rule=polymorph_exclusion(p, cutoff_mev=cutoff_mev, hull_key=hull_key),
        dimensionality=p.dimensionality,
    )


def summarize_group(
    group: CompositionGroup,
    *,
    scored: Polymorph | None,
    cutoff_mev: float | None,
    reference_values: list[ReferenceValue] | None = None,
    hull_key: str = MIXED_HULL,
) -> CompositionSummary:
    polys = mp_polymorphs(group, hull_key)
    by_id = {p.ids.mp: p for p in polys}

    def row_for(mp_id: str | None) -> PolymorphSummaryRow | None:
        p = by_id.get(mp_id) if mp_id else None
        return None if p is None else summary_row(p, cutoff_mev=cutoff_mev, hull_key=hull_key)

    summary = PolymorphSummary(
        composition_id=group.composition,
        total=len(polys),
        observed_count=sum(1 for p in polys if p.observed is True),
        theoretical_count=sum(1 for p in polys if p.theoretical is True),
        unknown_count=sum(1 for p in polys if p.observed is None),
        ground_state=row_for(group.ground_state_mp),
        ground_state_is_theoretical=group.ground_state_is_theoretical,
        lowest_observed=row_for(group.lowest_observed_mp),
        scored=None if scored is None else summary_row(scored, cutoff_mev=cutoff_mev),
        top_by_hull=[
            summary_row(p, cutoff_mev=cutoff_mev, hull_key=hull_key) for p in polys[:TOP_N]
        ],
    )
    return CompositionSummary(
        composition=group.composition,
        polymorphs=summary,
        experimental_gaps=group.experimental_gaps,
        reference_values=list(reference_values or []),
        hazard=group.hazard,
        literature=group.literature,
    )
