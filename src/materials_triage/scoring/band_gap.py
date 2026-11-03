"""Band gap policy: which value scores, from which source, and what the row says about it.

Sources, in the profile's `source_order` (default experimental, tbmbj, pbe):
- experimental: the composition-level pool of compendium values and entered reference values.
  Point values form the aggregate (median by default, minimum as the conservative option);
  ranges widen the shown min and max and count as sources but do not enter the aggregate.
- tbmbj: the JARVIS TBmBJ gap matched onto the scored polymorph.
- pbe: the Materials Project summary gap of the scored polymorph.

`pbe_only` uses the PBE value alone. `best_available` takes the first source with a value.
When experimental and TBmBJ are both present and `conflict_tolerance_ev` is set, a difference
above it flags `band_gap_conflict` and applies `on_conflict` (next source in order, or the
minimum of the two). Without a tolerance the two are shown but not compared, and the row says
so. One source only flags `band_gap_single_source`. The hard window is the stricter of the
profile's and the query's; outside it the candidate is excluded.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from materials_triage.config.schema import Aggregate, BandGapPolicy, BandGapSettings, OnConflict
from materials_triage.records import (
    ExperimentalGapAggregate,
    Polymorph,
    Provenance,
    ReferenceValue,
    Value,
)
from materials_triage.records.bundle import Caveat, CaveatId, Exclusion, ExclusionRule, Flag
from materials_triage.scoring.criteria import CriterionResult, clamp01

TBMBJ_KEY = "jarvis_tbmbj"
PBE_KEY = "mp_summary"


@dataclass(frozen=True)
class SourceValue:
    source: str  # experimental_median | experimental_minimum | tbmbj | pbe
    value: float
    unit: str
    provenance: Provenance
    detail: str


@dataclass(frozen=True)
class ExperimentalPool:
    points: list[float]
    low: float | None
    high: float | None
    n_sources: int
    provenances: list[Provenance]
    forms: list[str]


def experimental_pool(
    aggregate: ExperimentalGapAggregate | None, references: list[ReferenceValue]
) -> ExperimentalPool:
    points: list[float] = []
    lows: list[float] = []
    highs: list[float] = []
    provs: list[Provenance] = []
    forms: list[str] = []
    if aggregate is not None:
        for eg in aggregate.values:
            if eg.value_ev.value is not None:
                points.append(float(eg.value_ev.value))
                lows.append(float(eg.value_ev.value))
                highs.append(float(eg.value_ev.value))
                provs.append(eg.value_ev.provenance)
                forms.append("compendium")
    for rv in references:
        if rv.property != "band_gap_ev" or rv.status != "entered":
            continue
        if rv.value is not None and rv.value.value is not None:
            points.append(float(rv.value.value))
            lows.append(float(rv.value.value))
            highs.append(float(rv.value.value))
            provs.append(rv.provenance)
            forms.append(rv.form)
        elif rv.value_range is not None:
            lows.append(float(rv.value_range[0]))
            highs.append(float(rv.value_range[1]))
            provs.append(rv.provenance)
            forms.append(rv.form)
    return ExperimentalPool(
        points=points,
        low=min(lows) if lows else None,
        high=max(highs) if highs else None,
        n_sources=len(provs),
        provenances=provs,
        forms=forms,
    )


def _experimental(pool: ExperimentalPool, aggregate: Aggregate) -> SourceValue | None:
    if not pool.points:
        return None
    if aggregate is Aggregate.MINIMUM:
        value, name = min(pool.points), "experimental_minimum"
    else:
        value, name = float(statistics.median(pool.points)), "experimental_median"
    # The provenance of the aggregate is the record whose value is closest to it, lowest first.
    closest = min(
        range(len(pool.points)), key=lambda i: (abs(pool.points[i] - value), pool.points[i])
    )
    detail = (
        f"{name.split('_')[1]} of {len(pool.points)} measured values"
        f" ({pool.low:g} to {pool.high:g} eV across {pool.n_sources} sources)"
        if pool.low is not None and pool.high is not None
        else name
    )
    return SourceValue(name, value, "eV", pool.provenances[closest], detail)


def _from_polymorph(p: Polymorph | None, key: str, name: str) -> SourceValue | None:
    if p is None:
        return None
    v: Value[float] | None = p.band_gap.get(key)
    if v is None or v.value is None:
        return None
    return SourceValue(name, float(v.value), v.unit, v.provenance, f"{key} on {p.ids.mp}")


@dataclass(frozen=True)
class BandGapOutcome:
    result: CriterionResult
    source_used: str | None
    conflict: bool
    candidates: dict[str, SourceValue]


def band_gap(
    scored: Polymorph | None,
    *,
    experimental: ExperimentalGapAggregate | None,
    references: list[ReferenceValue],
    settings: BandGapSettings,
    query_min_ev: float | None,
    query_max_ev: float | None,
    source_ref: str,
    standing_caveat_ref: str | None,
) -> BandGapOutcome:
    pool = experimental_pool(experimental, references)
    found: dict[str, SourceValue] = {}
    exp = _experimental(pool, settings.aggregate)
    if exp is not None:
        found["experimental"] = exp
    tb = _from_polymorph(scored, TBMBJ_KEY, "tbmbj")
    if tb is not None:
        found["tbmbj"] = tb
    pbe = _from_polymorph(scored, PBE_KEY, "pbe")
    if pbe is not None:
        found["pbe"] = pbe

    notes: list[str] = []
    flags: list[Flag] = []
    caveats: list[Caveat] = []
    if pool.n_sources and exp is not None:
        caveats.append(Caveat(id=CaveatId.EXPERIMENTAL_GAP_COMPOSITION_LEVEL))
        if any(f == "compendium" for f in pool.forms):
            caveats.append(Caveat(id=CaveatId.EXPERIMENTAL_GAP_UNREFERENCED))
    elif pool.n_sources:
        notes.append(
            f"experimental sources give only ranges ({pool.low:g} to {pool.high:g} eV); "
            "no point value to aggregate"
        )
    for name, sv in found.items():
        notes.append(f"{name}: {sv.value:.3f} eV ({sv.detail})")

    conflict = False
    order = list(settings.source_order)
    if settings.policy is BandGapPolicy.PBE_ONLY:
        order = ["pbe"]
    elif exp is not None and tb is not None:
        if settings.conflict_tolerance_ev is None:
            flags.append(Flag.BAND_GAP_SOURCES_UNCOMPARED)
            notes.append(
                "experimental and TBmBJ values shown side by side; conflict tolerance not "
                "configured, so they are not compared"
            )
        elif abs(exp.value - tb.value) > settings.conflict_tolerance_ev:
            conflict = True
            flags.append(Flag.BAND_GAP_CONFLICT)
            notes.append(
                f"sources conflict: experimental {exp.value:.3f} eV vs TBmBJ {tb.value:.3f} eV "
                f"differ by more than {settings.conflict_tolerance_ev:g} eV"
            )
            if settings.on_conflict is OnConflict.MINIMUM:
                low = min((exp, tb), key=lambda s: s.value)
                found["conflict_minimum"] = SourceValue(
                    "conflict_minimum", low.value, low.unit, low.provenance, low.detail
                )
                order = ["conflict_minimum", *[s for s in order if s != "experimental"]]
            else:
                order = [s for s in order if s != "experimental"]
    if len(found) == 1:
        flags.append(Flag.BAND_GAP_SINGLE_SOURCE)

    chosen = next((found[s] for s in order if s in found), None)
    if standing_caveat_ref is not None:
        caveats.append(Caveat(id=CaveatId.BAND_OFFSETS_NOT_CHECKED, source_ref=standing_caveat_ref))
    if chosen is None:
        return BandGapOutcome(
            CriterionResult(
                normalized=None,
                source=None,
                missing_reason="no band gap from any source in policy order",
                flags=tuple(flags),
                caveats=tuple(caveats),
                notes=tuple(notes),
            ),
            None,
            conflict,
            found,
        )

    hard_min = _stricter_min(settings.hard_min_ev, query_min_ev, notes)
    hard_max = _stricter_max(settings.hard_max_ev, query_max_ev, notes)
    exclusion: Exclusion | None = None
    if hard_min is not None and chosen.value < hard_min:
        exclusion = Exclusion(
            rule=ExclusionRule.BAND_GAP_HARD_MIN,
            detail=f"{chosen.value:.3f} eV ({chosen.source}) is below the {hard_min:g} eV minimum",
            source_ref=source_ref,
        )
    elif hard_max is not None and chosen.value > hard_max:
        exclusion = Exclusion(
            rule=ExclusionRule.BAND_GAP_HARD_MAX,
            detail=f"{chosen.value:.3f} eV ({chosen.source}) is above the {hard_max:g} eV maximum",
            source_ref=source_ref,
        )
    normalized: float | None
    if exclusion is not None:
        normalized = None
    elif settings.soft_preference_start_ev is not None and settings.soft_preference_start_ev > 0:
        normalized = clamp01(chosen.value / settings.soft_preference_start_ev)
    else:
        normalized = 1.0
    return BandGapOutcome(
        CriterionResult(
            normalized=normalized,
            raw_value=chosen.value,
            raw_unit=chosen.unit,
            source=chosen.source,
            provenance=chosen.provenance,
            exclusion=exclusion,
            flags=tuple(flags),
            caveats=tuple(caveats),
            notes=tuple(notes),
        ),
        chosen.source,
        conflict,
        found,
    )


def _stricter_min(profile: float | None, query: float | None, notes: list[str]) -> float | None:
    if query is None:
        return profile
    if profile is None or query > profile:
        return query
    notes.append(f"query band_gap_min_ev {query:g} is looser than the profile's {profile:g}; kept")
    return profile


def _stricter_max(profile: float | None, query: float | None, notes: list[str]) -> float | None:
    if query is None:
        return profile
    if profile is None or query < profile:
        return query
    notes.append(f"query band_gap_max_ev {query:g} is looser than the profile's {profile:g}; kept")
    return profile
