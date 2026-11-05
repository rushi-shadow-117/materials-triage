"""View models: what the templates iterate over. Built from the bundle only; every number is
already a display string from `precision`, every caveat already resolved text."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from materials_triage.adapters.common import try_reduced_formula
from materials_triage.records import Provenance, record_url
from materials_triage.records.bundle import (
    UNRESOLVED_REASON,
    Anchor,
    Candidate,
    CaveatId,
    CriterionScore,
    EvidenceHit,
    EvidenceLabel,
    Flag,
    ProvenanceBundle,
)
from materials_triage.render import precision
from materials_triage.render.caveats import (
    NO_KEY_CAVEAT,
    PROFILE_WIDE,
    CaveatConfig,
    CaveatText,
    key_caveat,
    promoted_ids,
    row_specific,
)
from materials_triage.render.tokens import (
    CRITERION_LABELS,
    TIES_NOTE,
    BundleIndex,
    TokenError,
    anchor_placement,
    ghs_text,
    hide_record_ids,
    render_text,
)
from materials_triage.scoring.scorer import weighted_total

MAX_EXCLUDED_SHOWN = 50  # the CSV export carries every row
TIER_ORDER = (
    EvidenceLabel.DIELECTRIC_CHARACTERIZED,
    EvidenceLabel.THIN_FILM_DEPOSITED,
    EvidenceLabel.BULK_SYNTHESIZED,
    EvidenceLabel.COMPUTED_ONLY,
    EvidenceLabel.NOT_RELEVANT,
    EvidenceLabel.NO_ABSTRACT,
    EvidenceLabel.UNCLASSIFIED,
)


@dataclass(frozen=True)
class ProvenanceView:
    source: str
    record_id: str
    method: str | None
    fetched_at: str
    source_version: str | None
    url: str | None
    license: str | None
    fetch_label: str = "fetched"  # "recorded" for a replayed recording (review F15)

    @classmethod
    def build(cls, p: Provenance, method: str | None = None) -> ProvenanceView:
        return cls(
            p.source,
            p.source_record_id,
            method,
            p.fetched_at.isoformat(),
            p.source_version,
            record_url(p),
            p.license,
            "recorded" if p.recorded else "fetched",
        )


@dataclass(frozen=True)
class ValueView:
    label: str
    text: str  # formatted number with unit, or the missing marker
    provenance: ProvenanceView | None


@dataclass(frozen=True)
class CriterionView:
    criterion: str
    label: str
    raw: str
    source: str
    normalized: str
    weight: str
    contribution: str
    missing: bool
    missing_reason: str | None
    provenance: ProvenanceView | None
    notes: list[str]


@dataclass(frozen=True)
class PolymorphRowView:
    mp_id: str
    spacegroup: str
    hull: str
    observed: str
    excluded_rule: str | None
    hull_provenance: ProvenanceView | None


@dataclass(frozen=True)
class PolymorphView:
    total: str
    observed: str
    theoretical: str
    unknown: str
    ground_state: PolymorphRowView | None
    ground_state_is_theoretical: bool | None
    lowest_observed: PolymorphRowView | None
    scored_is_ground_state: bool
    hull_status_conflict: bool
    top_by_hull: list[PolymorphRowView]


@dataclass(frozen=True)
class EvidenceView:
    openalex_id: str
    label: str
    deposition_method: str | None
    quote: str | None
    verified: bool
    note: str | None
    title: str | None
    year: str | None
    url: str | None


@dataclass
class RowView:
    composition: str
    is_anchor: bool
    rank: str
    total: str
    rationale: str
    rationale_verified: bool | None
    removed_fragments: list[str]
    key_caveat: str
    caveats: list[CaveatText]
    flags: list[str]
    evidence_tier: str
    k: str
    missing: list[str]
    exclusion: str | None
    exclusion_detail: str | None
    exclusion_ref: str | None
    criteria: list[CriterionView]
    polymorphs: PolymorphView
    ghs: str
    echa_attribution: bool
    gaps: str
    gap_values: list[ValueView]
    reference_values: list[ValueView]
    literature: str
    evidence: list[EvidenceView]
    sensitivity: str | None
    band_gap_source: str | None
    dimensionality: str = "missing"
    tied: bool = False


@dataclass
class RunView:
    rows: list[RowView]  # ranked order
    excluded: list[RowView]
    anchors: list[RowView]
    refusal: str | None = None
    missing_properties: list[str] = field(default_factory=list)
    partial_reasons: list[str] = field(default_factory=list)
    clamps: list[str] = field(default_factory=list)
    defaults_applied: list[str] = field(default_factory=list)
    budgets: list[str] = field(default_factory=list)
    caveat_texts: dict[str, CaveatText] = field(default_factory=dict)
    hidden_ranked: int = 0  # ranked rows beyond top_n, not shown
    hidden_excluded: int = 0
    hidden_unchecked: int = 0  # of the hidden ranked rows, those scored on summary data only
    excluded_by_rule: list[ExcludedCount] = field(default_factory=list)
    # the PI view names only excluded rows the PI listed; every other exclusion is a count
    excluded_named: list[RowView] = field(default_factory=list)
    hull_cutoff: str | None = None  # the effective energy above hull cutoff
    overview: str | None = None  # the verified summary:overview rationale slot
    unresolved_candidates: list[str] = field(default_factory=list)
    # each unmatched or unavailable entry with the reason on its chip
    unresolved: list[dict[str, str]] = field(default_factory=list)
    unavailable_properties: list[str] = field(default_factory=list)
    ties_note: str | None = None  # shown under the table when any shown rows are tied
    # caveats every row carries by construction, shown once above the table
    profile_caveats: list[CaveatText] = field(default_factory=list)
    hazard_attribution: str | None = None  # the ECHA attribution for GHS hazard data
    # band gap versus dielectric constant for every scored candidate that has both (Track H)
    chart: ChartView | None = None


@dataclass(frozen=True)
class ExcludedCount:
    rule: str
    count: int


def _listed_keys(bundle: ProvenanceBundle) -> set[str]:
    """Compositions the PI named: the candidate list and any extra anchors (review F17)."""
    settings = bundle.criteria.effective_settings
    names: list[str] = []
    for key in ("candidate_list", "extra_anchors"):
        value = settings.get(key)
        if isinstance(value, list):
            names.extend(str(v) for v in value)
    out = set()
    for n in names:
        reduced = try_reduced_formula(n)
        out.add(reduced if reduced is not None else n)
    return out


def _excluded_counts(excluded: list[Candidate]) -> list[ExcludedCount]:
    counts: dict[str, int] = {}
    for c in excluded:
        if c.excluded is not None:
            counts[c.excluded.rule.value] = counts.get(c.excluded.rule.value, 0) + 1
    return [ExcludedCount(r, n) for r, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


@dataclass(frozen=True)
class ChartTick:
    value: float  # position on the axis, in the displayed unit
    text: str  # the label, formatted by code


@dataclass(frozen=True)
class ChartPoint:
    """One candidate on the selection chart. `gap` is the scored band gap raw value (the
    band gap criterion); `k` is the scored polymorph's Materials Project DFPT total dielectric
    constant with its own provenance, not the dielectric criterion, which is missing while
    its target band is pending."""

    composition: str
    status: str  # shortlist | ranked | excluded | anchor
    gap: float  # in the displayed unit, for position
    gap_text: str
    gap_source: str
    k: float
    k_text: str
    k_source: str
    record_ids: list[str]  # gap record, k record; empty in the PI view


@dataclass(frozen=True)
class ChartView:
    points: list[ChartPoint]
    unplotted: list[str]  # shown rows and anchors only: "HfO2: no dielectric constant ..."
    x_label: str
    y_label: str
    x_ticks: list[ChartTick]
    y_ticks: list[ChartTick]
    # rows not named above: beyond top N without a k value, or never cross-checked
    others_not_plotted: int = 0


def cross_checked(row: Candidate | Anchor) -> bool:
    """The row's composition was enriched (hazard record, structure, literature fetched);
    a row without it was scored on summary data alone."""
    return Flag.ENRICHMENT_MISSING not in row.flags


def _excluded_order(excluded: list[Candidate]) -> list[Candidate]:
    """Cross-checked exclusions first (the candidates that came near the top), then by the
    weighted mean the excluded row's kept breakdown would give; a sort key only, never shown.
    Ties by composition, so the order is deterministic."""

    def key(c: Candidate) -> tuple[int, float, str]:
        would = weighted_total(c.score.criteria) if c.score is not None else None
        return (
            0 if cross_checked(c) else 1,
            -(would if would is not None else -1.0),
            c.composition,
        )

    return sorted(excluded, key=key)


def _chart(
    bundle: ProvenanceBundle,
    shown_ranked: list[Candidate],
    ranked_all: list[Candidate],
    excluded_all: list[Candidate],
    units: str,
    hide_ids: bool,
) -> ChartView:
    shown = {c.composition for c in shown_ranked}
    # cross-checked rows only: a row scored on summary data alone was never checked for
    # hazard or structure and is not compared against (Track H sweep)
    rows: list[tuple[str, Candidate | Anchor]] = [
        *(
            ("shortlist" if c.composition in shown else "ranked", c)
            for c in ranked_all
            if cross_checked(c)
        ),
        *(("excluded", c) for c in excluded_all if cross_checked(c)),
        *(("anchor", a) for a in bundle.anchors),
    ]
    named = shown | {a.composition for a in bundle.anchors}
    points: list[ChartPoint] = []
    unplotted: list[str] = []
    not_named = 0
    for status, row in rows:
        gap_score = next(
            (cs for cs in (row.score.criteria if row.score else []) if cs.criterion == "band_gap"),
            None,
        )
        scored = row.group.polymorphs.scored
        k_value = scored.dielectric.get("e_total") if scored is not None else None
        reason = None
        if gap_score is None or gap_score.raw_value is None:
            reason = "no band gap value"
        elif k_value is None or k_value.value is None:
            reason = "no dielectric constant in the configured sources"
        if reason is not None:
            if row.composition in named:
                unplotted.append(f"{row.composition}: {reason}")
            else:
                not_named += 1
            continue
        assert gap_score is not None and gap_score.raw_value is not None
        assert k_value is not None and k_value.value is not None
        factor, _label = precision.display_unit(gap_score.raw_unit, units)
        ids: list[str] = []
        if not hide_ids:
            if gap_score.provenance is not None:
                ids.append(gap_score.provenance.source_record_id)
            ids.append(k_value.provenance.source_record_id)
        points.append(
            ChartPoint(
                composition=row.composition,
                status=status,
                gap=float(Decimal(str(gap_score.raw_value)) * factor),
                gap_text=precision.fmt(gap_score.raw_value, gap_score.raw_unit, units),
                gap_source=gap_score.source or "none",
                k=float(k_value.value),
                k_text=precision.fmt(k_value.value, k_value.unit, units),
                k_source=f"{k_value.provenance.source} {k_value.method or ''}".strip(),
                record_ids=ids,
            )
        )
    unchecked = sum(1 for c in [*ranked_all, *excluded_all] if not cross_checked(c))
    gap_unit = precision.display_unit("eV", units)[1] or "eV"
    return ChartView(
        points=points,
        unplotted=unplotted,
        others_not_plotted=not_named + unchecked,
        x_label=f"band gap ({gap_unit})",
        y_label="dielectric constant k (computed, DFPT)",
        x_ticks=_ticks([p.gap for p in points], "eV", units),
        y_ticks=_ticks([p.k for p in points], "1", units),
    )


def _ticks(values: list[float], unit: str, units: str) -> list[ChartTick]:
    """Five round axis labels from 0 to just above the largest value, formatted by code.
    Positions are in the displayed unit, as the point coordinates are."""
    if not values:
        return []
    top = max(values)
    if top <= 0:
        return [ChartTick(0.0, "0")]
    raw_step = top / 4
    magnitude = Decimal(10) ** (Decimal(str(raw_step)).adjusted())
    step = next(
        float(magnitude * m)
        for m in (Decimal(1), Decimal(2), Decimal(5), Decimal(10))
        if float(magnitude * m) >= raw_step
    )
    ticks: list[ChartTick] = []
    # as many decimals as the step needs ("5", not "5.00 eV"); the axis title carries the
    # unit, and a unit on every tick clipped the last label at the right edge
    places = max(0, -Decimal(str(step)).normalize().as_tuple().exponent)  # type: ignore[operator]
    v = 0.0
    while v < top + step:
        # tick values are already in the displayed unit; format them without re-conversion
        ticks.append(ChartTick(v, precision.quantize(Decimal(str(v)), places)))
        v = float(Decimal(str(v)) + Decimal(str(step)))
    return ticks


def _fmt(value: float | int | None, unit: str | None, units: str) -> str:
    return "missing" if value is None else precision.fmt(value, unit, units)


def _criterion_view(cs: CriterionScore, units: str) -> CriterionView:
    raw = "missing" if cs.raw_value is None else precision.fmt(cs.raw_value, cs.raw_unit, units)
    if cs.raw_value is None and cs.missing_reason:
        raw = f"missing ({cs.missing_reason})"
    return CriterionView(
        criterion=cs.criterion,
        label=CRITERION_LABELS.get(cs.criterion, cs.criterion),
        raw=raw,
        source=cs.source or "none",
        normalized="missing" if cs.normalized is None else precision.fmt(cs.normalized, "score"),
        weight=precision.fmt(cs.weight, "score"),
        contribution=precision.fmt(cs.contribution, "score"),
        missing=cs.missing,
        missing_reason=cs.missing_reason,
        provenance=ProvenanceView.build(cs.provenance, cs.source) if cs.provenance else None,
        notes=list(cs.notes),
    )


def _polymorph_row(row, units: str) -> PolymorphRowView:  # type: ignore[no-untyped-def]
    hull = row.hull_energy
    observed = (
        "unknown" if row.observed is None else ("observed" if row.observed else "not observed")
    )
    return PolymorphRowView(
        mp_id=row.mp_id or "no MP id",
        spacegroup=row.spacegroup_symbol or "not reported",
        hull="missing"
        if hull is None or hull.value is None
        else precision.fmt(hull.value, hull.unit, units),
        observed=observed,
        excluded_rule=row.excluded_rule.value if row.excluded_rule else None,
        hull_provenance=ProvenanceView.build(hull.provenance, hull.method) if hull else None,
    )


def _polymorph_view(row: Candidate | Anchor, units: str) -> PolymorphView:
    p = row.group.polymorphs
    scored_id = p.scored.mp_id if p.scored else None
    ground_id = p.ground_state.mp_id if p.ground_state else None
    return PolymorphView(
        total=precision.quantize(p.total, 0),
        observed=precision.quantize(p.observed_count, 0),
        theoretical=precision.quantize(p.theoretical_count, 0),
        unknown=precision.quantize(p.unknown_count, 0),
        ground_state=_polymorph_row(p.ground_state, units) if p.ground_state else None,
        ground_state_is_theoretical=p.ground_state_is_theoretical,
        lowest_observed=_polymorph_row(p.lowest_observed, units) if p.lowest_observed else None,
        scored_is_ground_state=scored_id == ground_id,
        hull_status_conflict=any(r.hull_status_conflict for r in p.top_by_hull),
        top_by_hull=[_polymorph_row(r, units) for r in p.top_by_hull],
    )


EVIDENCE_DROPPED = "Evidence not used in this run"


def _evidence_dropped(bundle: ProvenanceBundle) -> bool:
    """The run left evidence out of every row (all-or-none, agent/pipeline.py); a row's labels
    are then shown as not used, never as the tier that would have scored."""
    return any(r.startswith(EVIDENCE_DROPPED) for r in bundle.run.partial_reasons)


def _evidence_tier(hits: list[EvidenceHit]) -> str:
    verified = [h.label for h in hits if h.verified]
    for label in TIER_ORDER:
        if label in verified:
            return label.value
    if hits and all(h.label is EvidenceLabel.UNCLASSIFIED for h in hits):
        return "unclassified"
    if hits and all(h.label is EvidenceLabel.NO_ABSTRACT for h in hits):
        return "no abstract"
    if hits:
        return "no verified evidence"
    return "no abstracts"


def _evidence_views(row: Candidate | Anchor, hits: list[EvidenceHit]) -> list[EvidenceView]:
    titles = {}
    if row.group.literature is not None:
        titles = {h.openalex_id: h for h in row.group.literature.hits}
    out = []
    for h in hits:
        lit = titles.get(h.openalex_id)
        out.append(
            EvidenceView(
                openalex_id=h.openalex_id,
                label=h.label.value,
                deposition_method=h.deposition_method,
                quote=h.supporting_sentence,
                verified=h.verified,
                note=h.verifier_note,
                title=lit.title if lit else None,
                year=precision.quantize(lit.year, 0) if lit and lit.year is not None else None,
                url=lit.landing_page_url if lit else None,
            )
        )
    return out


def _row_view(
    row: Candidate | Anchor,
    bundle: ProvenanceBundle,
    index: BundleIndex,
    caveats: CaveatConfig,
    units: str,
    hide_ids: bool = False,
    wide: frozenset[CaveatId] = PROFILE_WIDE,
) -> RowView:
    comp = row.composition
    is_anchor = isinstance(row, Anchor)
    hits = [e for e in bundle.evidence if e.composition == comp]
    # the row's own caveats; ids every shown ranked row carries show once above the table
    # (RunView.profile_caveats), any other profile-wide id stays on the rows that carry it
    resolved = [caveats.resolve(c, row) for c in row_specific(row.caveats, wide)]
    key = key_caveat(row.caveats)
    slot_id = f"candidate:{comp}:one_line"
    slot = bundle.rationale.get(slot_id)
    rationale = ""
    if slot is not None and slot.text:
        try:
            rationale = render_text(index, slot.text, units=units, hide_ids=hide_ids)
        except TokenError as e:
            rationale = f"(rationale withheld: {e})"
    criteria = [_criterion_view(cs, units) for cs in row.score.criteria] if row.score else []
    k = "missing"
    if row.score is not None:
        for cs in row.score.criteria:
            if cs.criterion == "dielectric_constant" and cs.raw_value is not None:
                k = precision.fmt(cs.raw_value, cs.raw_unit, units)
    dropped = _evidence_dropped(bundle)
    # evidence left out of the whole run is said once, in the Evidence column ("not used this
    # run"); listing it as missing on every row as well read as a per-row data gap
    missing = [
        c.label
        for c in criteria
        if c.missing and c.weight != "0.000" and not (dropped and c.criterion == "evidence")
    ]
    g = row.group
    gap_score = next(
        (cs for cs in (row.score.criteria if row.score else []) if cs.criterion == "band_gap"),
        None,
    )
    used_ids = set(gap_score.used_record_ids) if gap_score is not None else set()

    def _use(provenance_id: str) -> str:
        # bundles written before used_record_ids existed say nothing rather than "not used"
        if not used_ids:
            return ""
        return ", used" if provenance_id in used_ids else ", not used"

    gaps = "none in the public gap tables"
    gap_values: list[ValueView] = []
    if g.experimental_gaps is not None:
        eg = g.experimental_gaps
        gaps = (
            f"{precision.fmt(eg.min, 'eV', units)} to {precision.fmt(eg.max, 'eV', units)} "
            f"across {precision.quantize(eg.n, 0)} value(s), median "
            f"{precision.fmt(eg.median, 'eV', units)}"
        )
        gap_values = [
            ValueView(
                f"{v.table} (compendium{_use(v.value_ev.provenance.source_record_id)})",
                _fmt(v.value_ev.value, v.value_ev.unit, units),
                ProvenanceView.build(v.value_ev.provenance, v.value_ev.method),
            )
            for v in eg.values
        ]
    refs = [
        ValueView(
            f"{r.entry_id} ({r.form}, {r.status}{_use(r.provenance.source_record_id)})",
            (
                _fmt(r.value.value, r.value.unit, units)
                if r.value is not None
                else (
                    f"{precision.fmt(r.value_range[0], 'eV', units)} to "
                    f"{precision.fmt(r.value_range[1], 'eV', units)}"
                    if r.value_range
                    else "missing"
                )
            ),
            ProvenanceView.build(r.provenance),
        )
        for r in g.reference_values
    ]
    lit = g.literature
    literature = "no literature search"
    if lit is not None:
        matched = (
            "not reported"
            if lit.matched_total is None
            else precision.quantize(lit.matched_total, 0)
        )
        with_abs = (
            "not reported"
            if lit.matched_with_abstract is None
            else precision.quantize(lit.matched_with_abstract, 0)
        )
        literature = (
            f"{matched} matched, {with_abs} with abstracts, {precision.quantize(len(lit.hits), 0)} "
            f"read ({lit.scope}; query {lit.query!r})"
        )
    if is_anchor:
        assert isinstance(row, Anchor)
        rank = anchor_placement(row) or "anchor"
        excluded = row.excluded
    else:
        assert isinstance(row, Candidate)
        shown_rank = index.ranks.get(comp)
        rank = (
            "excluded"
            if row.rank is None
            else (shown_rank.text if shown_rank else precision.quantize(row.rank, 0))
        )
        excluded = row.excluded
    sensitivity = None
    if isinstance(row, Candidate) and row.sensitivity is not None:
        s = row.sensitivity
        sensitivity = (
            f"rank {s.rank_min} to {s.rank_max} over {s.perturbations} perturbations"
            f" ({'stable' if s.stable else 'unstable'})"
        )
    return RowView(
        composition=comp,
        is_anchor=is_anchor,
        tied=bool(not is_anchor and index.ranks.get(comp) and index.ranks[comp].tied),
        rank=rank,
        total="excluded"
        if row.score is None or row.score.total is None
        else precision.fmt(row.score.total, "score"),
        rationale=rationale,
        rationale_verified=slot.verified if slot else None,
        removed_fragments=list(slot.removed_fragments) if slot else [],
        key_caveat=caveats.resolve(key, row).text if key is not None else NO_KEY_CAVEAT,
        caveats=resolved,
        flags=[f.value for f in row.flags],
        evidence_tier=("not used this run" if dropped and hits else _evidence_tier(hits)),
        k=k,
        missing=missing,
        exclusion=excluded.rule.value if excluded else None,
        exclusion_detail=(hide_record_ids(excluded.detail) if hide_ids else excluded.detail)
        if excluded
        else None,
        exclusion_ref=excluded.source_ref if excluded else None,
        criteria=criteria,
        polymorphs=_polymorph_view(row, units),
        ghs=ghs_text(row),
        echa_attribution=bool(g.hazard and g.hazard.echa_attribution_required),
        gaps=gaps,
        gap_values=gap_values,
        reference_values=refs,
        literature=literature,
        evidence=_evidence_views(row, hits),
        sensitivity=sensitivity,
        band_gap_source=row.score.band_gap_source if row.score else None,
        dimensionality=hide_record_ids(_dimensionality(row)) if hide_ids else _dimensionality(row),
    )


def _dimensionality(row: Candidate | Anchor) -> str:
    """The scored polymorph's structural dimensionality with its record, or why it is missing."""
    dim = row.score.dimensionality if row.score else None
    if dim is None:
        note = row.score.dimensionality_note if row.score else None
        return f"missing ({note or 'not computed'})"
    record = dim.provenance.source_record_id
    if dim.value is None:
        return f"missing ({dim.missing_reason}; {record})"
    return f"{precision.quantize(dim.value, 0)} ({dim.method}; {record})"


def build(
    bundle: ProvenanceBundle, caveats: CaveatConfig, *, units: str, hide_ids: bool = False
) -> RunView:
    index = BundleIndex.build(bundle, caveat_text=lambda c, row: caveats.resolve(c, row).text)
    top_n = bundle.criteria.effective_settings.get("top_n")
    limit = int(top_n) if isinstance(top_n, int) and top_n > 0 else None
    ranked_all = bundle.ranked()
    excluded_all = _excluded_order(bundle.excluded())
    shown_ranked = ranked_all[:limit] if limit else ranked_all
    shown_excluded = excluded_all[:MAX_EXCLUDED_SHOWN]
    wide = promoted_ids([c.caveats for c in shown_ranked])
    rows = [_row_view(c, bundle, index, caveats, units, hide_ids, wide) for c in shown_ranked]
    excluded = [_row_view(c, bundle, index, caveats, units, hide_ids, wide) for c in shown_excluded]
    listed = _listed_keys(bundle)
    excluded_named = [
        _row_view(c, bundle, index, caveats, units, hide_ids, wide)
        for c in excluded_all
        if c.composition in listed
    ]
    anchors = [_row_view(a, bundle, index, caveats, units, hide_ids, wide) for a in bundle.anchors]
    # the Caveats section defines what the shown ranked rows and anchors carry, not what only
    # an excluded row carries (Track H sweep)
    texts: dict[str, CaveatText] = {}
    for r in [*rows, *anchors]:
        for c in r.caveats:
            texts.setdefault(c.id.value, c)
    profile_caveats: dict[str, CaveatText] = {}
    every: list[Candidate | Anchor] = [*shown_ranked, *shown_excluded, *bundle.anchors]
    for brow in every:
        for cv in brow.caveats:
            if cv.id in wide and cv.id.value not in profile_caveats:
                profile_caveats[cv.id.value] = caveats.resolve(cv, brow)
    for cid, text in profile_caveats.items():
        texts.setdefault(cid, text)
    # the ECHA line is a data attribution, not a caveat: it reads as an orphan "Source: ..."
    # bullet in the list, so it shows as its own line naming what it attributes
    echa = profile_caveats.pop(CaveatId.ATTRIBUTION_ECHA.value, None)
    hazard_attribution = echa.text if echa is not None and echa.entered else None
    if any("band offset" in m.text.lower() for m in bundle.missing_properties):
        # already listed under "What this screen cannot tell you"
        profile_caveats.pop(CaveatId.BAND_OFFSETS_NOT_CHECKED.value, None)
    run = bundle.run
    budgets = [
        f"{k}: {precision.quantize(run.budgets_used.get(k, 0), 0)} of {precision.quantize(v, 0)}"
        for k, v in sorted(run.budgets_limit.items())
    ]
    refusal = None
    for entry in bundle.decision_log:
        if entry.step == "refused":
            refusal = str(entry.detail.get("text") or entry.summary)
    return RunView(
        rows=rows,
        excluded=excluded,
        anchors=anchors,
        refusal=refusal,
        missing_properties=[m.text for m in bundle.missing_properties],
        partial_reasons=list(run.partial_reasons),
        clamps=[
            f"{c.setting}: requested {c.requested}, applied {c.applied} ({c.bound})"
            for c in bundle.criteria.clamps
        ],
        defaults_applied=list(bundle.criteria.defaults_applied),
        budgets=budgets,
        caveat_texts=texts,
        hidden_ranked=len(ranked_all) - len(shown_ranked),
        hidden_excluded=len(excluded_all) - len(shown_excluded),
        hidden_unchecked=sum(1 for c in ranked_all[len(shown_ranked) :] if not cross_checked(c)),
        excluded_by_rule=_excluded_counts(excluded_all),
        excluded_named=excluded_named,
        hull_cutoff=_hull_cutoff(bundle, units),
        overview=_overview(bundle, index, units, hide_ids),
        unresolved_candidates=list(bundle.criteria.unresolved_candidates),
        unresolved=[
            *(
                {"text": t, "reason": UNRESOLVED_REASON}
                for t in bundle.criteria.unresolved_candidates
            ),
            *({"text": k, "reason": r} for k, r in bundle.criteria.not_fetched.items()),
        ],
        unavailable_properties=list(bundle.criteria.unavailable_properties),
        ties_note=TIES_NOTE if any(r.tied for r in rows) else None,
        profile_caveats=list(profile_caveats.values()),
        hazard_attribution=hazard_attribution,
        chart=_chart(bundle, shown_ranked, ranked_all, excluded_all, units, hide_ids),
    )


def _overview(
    bundle: ProvenanceBundle, index: BundleIndex, units: str, hide_ids: bool = False
) -> str | None:
    """The summary:overview slot, rendered from its tokens. A slot the verifier did not pass
    is not shown."""
    slot = bundle.rationale.get("summary:overview")
    if slot is None or not slot.text or slot.verified is False:
        return None
    try:
        return render_text(index, slot.text, units=units, hide_ids=hide_ids)
    except TokenError as e:
        return f"(overview withheld: {e})"


def _hull_cutoff(bundle: ProvenanceBundle, units: str) -> str | None:
    """The effective cutoff as stored in meV/atom, shown in the hull's unit (eV/atom)."""
    mev = bundle.criteria.stability_cutoff_mev
    if mev is None:
        return None
    return precision.fmt(mev / 1000.0, "eV/atom", units)
