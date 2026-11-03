"""View models: what the templates iterate over. Built from the bundle only; every number is
already a display string from `precision`, every caveat already resolved text."""

from __future__ import annotations

from dataclasses import dataclass, field

from materials_triage.records import Provenance
from materials_triage.records.bundle import (
    Anchor,
    Candidate,
    CriterionScore,
    EvidenceHit,
    EvidenceLabel,
    ProvenanceBundle,
)
from materials_triage.render import precision
from materials_triage.render.caveats import CaveatConfig, CaveatText
from materials_triage.render.tokens import (
    CRITERION_LABELS,
    BundleIndex,
    TokenError,
    ghs_text,
    render_text,
)

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

    @classmethod
    def build(cls, p: Provenance, method: str | None = None) -> ProvenanceView:
        return cls(
            p.source,
            p.source_record_id,
            method,
            p.fetched_at.isoformat(),
            p.source_version,
            p.url,
            p.license,
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
) -> RowView:
    comp = row.composition
    is_anchor = isinstance(row, Anchor)
    hits = [e for e in bundle.evidence if e.composition == comp]
    resolved = [caveats.resolve(c) for c in row.caveats]
    slot_id = f"candidate:{comp}:one_line"
    slot = bundle.rationale.get(slot_id)
    rationale = ""
    if slot is not None and slot.text:
        try:
            rationale = render_text(index, slot.text, units=units)
        except TokenError as e:
            rationale = f"(rationale withheld: {e})"
    criteria = [_criterion_view(cs, units) for cs in row.score.criteria] if row.score else []
    k = "missing"
    if row.score is not None:
        for cs in row.score.criteria:
            if cs.criterion == "dielectric_constant" and cs.raw_value is not None:
                k = precision.fmt(cs.raw_value, cs.raw_unit, units)
    missing = [c.label for c in criteria if c.missing and c.weight != "0.000"]
    g = row.group
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
                v.table,
                _fmt(v.value_ev.value, v.value_ev.unit, units),
                ProvenanceView.build(v.value_ev.provenance, v.value_ev.method),
            )
            for v in eg.values
        ]
    refs = [
        ValueView(
            f"{r.entry_id} ({r.form}, {r.status})",
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
        rank = (
            "anchor" if row.would_rank is None else f"would rank {row.would_rank} of {row.out_of}"
        )
        excluded = row.excluded
    else:
        assert isinstance(row, Candidate)
        rank = "excluded" if row.rank is None else precision.quantize(row.rank, 0)
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
        rank=rank,
        total="excluded"
        if row.score is None or row.score.total is None
        else precision.fmt(row.score.total, "score"),
        rationale=rationale,
        rationale_verified=slot.verified if slot else None,
        removed_fragments=list(slot.removed_fragments) if slot else [],
        key_caveat=resolved[0].text if resolved else "none",
        caveats=resolved,
        flags=[f.value for f in row.flags],
        evidence_tier=_evidence_tier(hits),
        k=k,
        missing=missing,
        exclusion=excluded.rule.value if excluded else None,
        exclusion_detail=excluded.detail if excluded else None,
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
    )


def build(bundle: ProvenanceBundle, caveats: CaveatConfig, *, units: str) -> RunView:
    index = BundleIndex.build(bundle)
    top_n = bundle.criteria.effective_settings.get("top_n")
    limit = int(top_n) if isinstance(top_n, int) and top_n > 0 else None
    ranked_all = bundle.ranked()
    excluded_all = bundle.excluded()
    shown_ranked = ranked_all[:limit] if limit else ranked_all
    shown_excluded = excluded_all[:MAX_EXCLUDED_SHOWN]
    rows = [_row_view(c, bundle, index, caveats, units) for c in shown_ranked]
    excluded = [_row_view(c, bundle, index, caveats, units) for c in shown_excluded]
    anchors = [_row_view(a, bundle, index, caveats, units) for a in bundle.anchors]
    texts: dict[str, CaveatText] = {}
    for r in [*rows, *excluded, *anchors]:
        for c in r.caveats:
            texts.setdefault(c.id.value, c)
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
    )
