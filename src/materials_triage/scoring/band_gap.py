"""Band gap policy: which value scores, from which source, and what the row says about it.

Sources, in the profile's `source_order` (default experimental, tbmbj, pbe):
- experimental: the composition-level pool of compendium values and entered reference values.
  Values are never aggregated across material forms: the first form in the profile's
  `preferred_forms` with a point value is used, and its point values form the aggregate
  (median by default, minimum as the conservative option). Ranges in that form widen the shown
  min and max and count as sources but do not enter the aggregate. Other forms are shown, not
  used.
- tbmbj: the JARVIS TBmBJ gap matched onto the scored polymorph.
- pbe: the Materials Project summary gap of the scored polymorph.

`pbe_only` uses the PBE value alone. `best_available` takes the first source with a value.
When experimental and TBmBJ are both present and `conflict_tolerance_ev` is set, a difference
above it flags `band_gap_conflict` and applies `on_conflict` (next source in order, or the
minimum of the two). Without a tolerance the two are shown but not compared, and the row says
so. One source only flags `band_gap_single_source`. The hard window is the stricter of the
profile's and the query's; outside it the candidate is excluded.

PBE-only window (owner decision 2026-11-04, extending the Track F prefilter principle): when
PBE is the only gap source, the profile's hard minimum excludes only below the profile's
`discovery_pbe_floor_ev`, the loosest admissible PBE value. Between the floor and the minimum
the candidate is kept, scored, and flagged `pbe_only_below_window`. A scientist's own minimum
applies to the value as written.
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


COMPENDIUM = "compendium"  # the experimental gap table's values: the form is not recorded


@dataclass(frozen=True)
class GapEntry:
    """One experimental value or range, with its material form. `used` is True only for the
    point values of the chosen form, the ones that enter the aggregate."""

    value: float | None  # None for a range
    low: float
    high: float
    form: str
    label: str  # the compendium table, or the reference entry id
    provenance: Provenance
    used: bool


@dataclass(frozen=True)
class ExperimentalPool:
    entries: list[GapEntry]
    form: str | None  # the form whose values are used; None when no form has a point value

    @property
    def chosen(self) -> list[GapEntry]:
        """Every entry of the chosen form (points and ranges); all entries when none is."""
        return [e for e in self.entries if self.form is None or e.form == self.form]

    @property
    def points(self) -> list[float]:
        return [e.value for e in self.entries if e.used and e.value is not None]

    @property
    def low(self) -> float | None:
        return min((e.low for e in self.chosen), default=None)

    @property
    def high(self) -> float | None:
        return max((e.high for e in self.chosen), default=None)

    @property
    def n_sources(self) -> int:
        return len(self.chosen)

    @property
    def other_forms(self) -> list[str]:
        return sorted({e.form for e in self.entries if e.form != self.form})


def experimental_pool(
    aggregate: ExperimentalGapAggregate | None,
    references: list[ReferenceValue],
    preferred_forms: tuple[str, ...] | list[str],
) -> ExperimentalPool:
    raw: list[tuple[float | None, float, float, str, str, Provenance]] = []
    if aggregate is not None:
        for eg in aggregate.values:
            if eg.value_ev.value is not None:
                v = float(eg.value_ev.value)
                raw.append((v, v, v, COMPENDIUM, eg.table, eg.value_ev.provenance))
    for rv in references:
        if rv.property != "band_gap_ev" or rv.status != "entered":
            continue
        if rv.value is not None and rv.value.value is not None:
            v = float(rv.value.value)
            raw.append((v, v, v, rv.form, rv.entry_id, rv.provenance))
        elif rv.value_range is not None:
            lo, hi = float(rv.value_range[0]), float(rv.value_range[1])
            raw.append((None, lo, hi, rv.form, rv.entry_id, rv.provenance))
    with_points = {r[3] for r in raw if r[0] is not None}
    order = [*preferred_forms, *sorted({r[3] for r in raw} - set(preferred_forms))]
    form = next((f for f in order if f in with_points), None)
    entries = [
        GapEntry(value, lo, hi, f, label, prov, used=value is not None and f == form)
        for value, lo, hi, f, label, prov in raw
    ]
    return ExperimentalPool(entries=entries, form=form)


def _experimental(pool: ExperimentalPool, aggregate: Aggregate) -> SourceValue | None:
    points = pool.points
    if not points or pool.form is None:
        return None
    if aggregate is Aggregate.MINIMUM:
        value, name = min(points), "experimental_minimum"
    else:
        value, name = float(statistics.median(points)), "experimental_median"
    # The provenance of the aggregate is the used record whose value is closest to it.
    used = [e for e in pool.entries if e.used and e.value is not None]
    closest = min(used, key=lambda e: (abs((e.value or 0.0) - value), e.value or 0.0))
    others = pool.other_forms
    detail = (
        f"{name.split('_')[1]} of {len(points)} measured value(s), form {pool.form}"
        f" ({pool.low:g} to {pool.high:g} eV across {pool.n_sources} source(s) in that form"
        + (f"; other forms shown, not used: {', '.join(others)}" if others else "")
        + ")"
    )
    return SourceValue(name, value, "eV", closest.provenance, detail)


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
    pool = experimental_pool(experimental, references, settings.preferred_forms)
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
        if pool.form == COMPENDIUM:
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

    if chosen.source.startswith("experimental"):
        used_ids = tuple(e.provenance.source_record_id for e in pool.entries if e.used)
    else:
        used_ids = (chosen.provenance.source_record_id,)
    hard_min = _stricter_min(settings.hard_min_ev, query_min_ev, notes)
    hard_max = _stricter_max(settings.hard_max_ev, query_max_ev, notes)
    exclusion: Exclusion | None = None
    pbe_window = (
        set(found) == {"pbe"}
        and chosen.source == "pbe"
        and hard_min is not None
        and hard_min == settings.hard_min_ev  # the profile's minimum binds, not the query's
        and settings.discovery_pbe_floor_ev is not None
        and settings.discovery_pbe_floor_ev <= chosen.value < hard_min
    )
    if pbe_window:
        flags.append(Flag.PBE_ONLY_BELOW_WINDOW)
        caveats.append(
            Caveat(
                id=CaveatId.PBE_ONLY_BELOW_WINDOW,
                source_ref=f"{source_ref}.pbe_only_caveat",
            )
        )
        notes.append(
            f"only a PBE gap ({chosen.value:.3f} eV): below the {hard_min:g} eV minimum but at or "
            f"above the {settings.discovery_pbe_floor_ev:g} eV PBE floor, so kept and flagged"
        )
    elif hard_min is not None and chosen.value < hard_min:
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
            used_record_ids=used_ids,
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
