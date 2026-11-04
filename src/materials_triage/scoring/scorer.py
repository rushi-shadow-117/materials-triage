"""Score, exclude, rank, and summarize a set of composition groups. Pure and deterministic.

One scoring path serves candidate lists and discovery: every input is a `CompositionGroup`.
Groups with only summary-level data (no thermo, hazard, or literature enrichment) score too:
their missing criteria stay missing, weights renormalize over the criteria that have values,
and the row is flagged `enrichment_missing`. The total is the weighted mean of the present
criteria. Ties break by composition string, then by the scored polymorph's MP id. Anchors are
scored by the same code and never take a slot.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime

from materials_triage.config.schema import CRITERIA, EffectiveConfig, SiteProfile
from materials_triage.records import CompositionGroup, Polymorph, ReferenceValue
from materials_triage.records.bundle import (
    Anchor,
    Candidate,
    Caveat,
    CaveatId,
    CriterionScore,
    DecisionLogEntry,
    EvidenceHit,
    Exclusion,
    ExclusionRule,
    Flag,
    MissingPropertyMarker,
    RankStability,
    ScoreBreakdown,
)
from materials_triage.scoring import criteria as crit
from materials_triage.scoring.band_gap import band_gap
from materials_triage.scoring.hazard import hazard
from materials_triage.scoring.polymorphs import (
    MIXED_HULL,
    mp_polymorphs,
    select_scored,
    summarize_group,
)
from materials_triage.scoring.profile import HazardPolicy, LoadedProfile

# When several rules exclude a candidate, the first in this order is the one shown.
EXCLUSION_ORDER = (
    ExclusionRule.HAZARD_RADIOACTIVE,
    ExclusionRule.HAZARD_EXCLUDE,
    ExclusionRule.HAZARD_ACUTE_ELEMENT,
    ExclusionRule.HAZARD_ACUTE_COMPOUND,
    ExclusionRule.HAZARD_ACUTE_GHS,
    ExclusionRule.STRUCTURE_MOLECULAR,
    ExclusionRule.STABILITY_CUTOFF,
    ExclusionRule.BAND_GAP_HARD_MIN,
    ExclusionRule.BAND_GAP_HARD_MAX,
    ExclusionRule.SIMPLICITY_MAX_ELEMENTS,
    ExclusionRule.SIMPLICITY_ANION_POLICY,
    ExclusionRule.EVIDENCE_TIER_MIN,
    ExclusionRule.DATA_NO_SCORABLE_CRITERIA,
)
SITE_PROFILE_REF = "site_profile.default.yaml#screen_cannot_tell_you"


@dataclass
class ScoringInputs:
    groups: list[CompositionGroup]
    requested_polymorphs: dict[str, str] = field(default_factory=dict)  # composition -> mp id
    reference_values: list[ReferenceValue] = field(default_factory=list)
    pending_reference_values: list[ReferenceValue] = field(default_factory=list)
    evidence: dict[str, list[EvidenceHit]] = field(default_factory=dict)


@dataclass
class Scored:
    composition: str
    group: CompositionGroup
    polymorph: Polymorph | None
    breakdown: ScoreBreakdown
    exclusion: Exclusion | None
    flags: list[Flag]
    caveats: list[Caveat]
    other_exclusions: list[Exclusion]

    @property
    def key(self) -> tuple[float, str, str]:
        total = self.breakdown.total if self.breakdown.total is not None else float("-inf")
        return (-total, self.composition, self.polymorph.ids.mp or "" if self.polymorph else "")


@dataclass
class ScoringResult:
    candidates: list[Candidate]
    anchors: list[Anchor]
    missing_properties: list[MissingPropertyMarker]
    decision_log: list[DecisionLogEntry]
    thermo_enrichment_ids: list[str]
    notes: list[str]


def weighted_total(scores: list[CriterionScore]) -> float | None:
    """Weighted mean over criteria that have a value and carry weight; None when none do."""
    present = [s for s in scores if s.weight > 0 and not s.missing and s.normalized is not None]
    if not present:
        return None
    return sum(s.contribution for s in present) / sum(s.weight for s in present)


def is_enriched(group: CompositionGroup) -> bool:
    """Summary-level groups carry only MP summary documents: no hazard, no literature, and no
    per-functional thermo rows."""
    return (
        group.hazard is not None
        or group.literature is not None
        or any(len(p.hull_energy) > 1 for p in group.polymorphs)
    )


def score_group(
    group: CompositionGroup,
    *,
    effective: EffectiveConfig,
    loaded: LoadedProfile,
    hazard_policy: HazardPolicy,
    site: SiteProfile,
    echa: tuple[str, str] | None,
    requested_mp: str | None,
    reference_values: list[ReferenceValue],
    pending_reference_values: list[ReferenceValue],
    evidence_hits: list[EvidenceHit] | None,
) -> Scored:
    profile = loaded.profile
    refs = loaded.source_refs
    scored = select_scored(group, requested_mp=requested_mp)
    enriched = is_enriched(group)
    results: dict[str, crit.CriterionResult] = {}

    cutoff = effective.stability_cutoff_mev
    hull = scored.hull_energy.get(profile.stability.hull) if scored is not None else None
    if cutoff is None:
        results["stability"] = crit.missing(
            "stability cutoff not entered", source=profile.stability.hull
        )
    else:
        results["stability"] = crit.stability(
            hull,
            cutoff_mev=cutoff,
            near_cutoff_band_mev=profile.stability.near_cutoff_band_mev_per_atom,
            source_ref=refs.get("stability", ""),
        )
    my_refs = [r for r in reference_values if r.composition == group.composition]
    gap = band_gap(
        scored,
        experimental=group.experimental_gaps,
        references=my_refs,
        settings=profile.band_gap,
        query_min_ev=effective.query.band_gap_min_ev,
        query_max_ev=effective.query.band_gap_max_ev,
        source_ref=refs.get("band_gap", ""),
        standing_caveat_ref=loaded.standing_caveats.get("band_offsets_not_checked"),
    )
    results["band_gap"] = gap.result
    results["hazard"] = hazard(
        group.composition,
        group.hazard,
        hazard_policy,
        exclude_radioactive=effective.exclude_radioactive,
        enrichment_fetched=enriched,
        echa_attribution=echa,
    )
    results["simplicity"] = crit.simplicity(
        group.composition, profile.simplicity, source_ref=refs.get("simplicity", "")
    )
    results["evidence"] = crit.evidence(
        evidence_hits,
        tiers=loaded.evidence_tiers,
        tier_min=effective.query.evidence_tier_min,
        literature=group.literature,
        source_ref=refs.get("evidence", ""),
    )
    results["dielectric_constant"] = crit.dielectric_constant(
        scored.dielectric.get("e_total") if scored is not None else None,
        target_band=profile.dielectric_constant.target_band,
    )
    results["deposition_method"] = crit.deposition_method(
        evidence_hits, site_methods=site.deposition_methods
    )
    results["cost"] = crit.cost()

    scores = [results[c].to_score(c, effective.weights.get(c, 0.0)) for c in CRITERIA]
    exclusions = [r.exclusion for r in results.values() if r.exclusion is not None]
    dim, dim_note, dim_exclusion = crit.structure(
        scored,
        exclude=profile.structure_exclude_dimensionality,
        source_ref=refs.get("structure", ""),
    )
    if dim_exclusion is not None:
        exclusions.append(dim_exclusion)
    flags: list[Flag] = [f for r in results.values() for f in r.flags]
    caveats: list[Caveat] = [c for r in results.values() for c in r.caveats]
    polys = mp_polymorphs(group)
    hull_conflict = any(p.hull_status_conflict for p in polys)
    if hull_conflict:
        flags.append(Flag.HULL_STATUS_CONFLICT)
    if group.ground_state_is_theoretical:
        flags.append(Flag.GROUND_STATE_IS_THEORETICAL)
    if requested_mp is not None:
        flags.append(Flag.POLYMORPH_REQUESTED)
    if profile.simplicity.anion_policy != "strict_oxide":
        # The stability cutoff was calibrated on binary oxides; say so on every row.
        caveats.append(
            Caveat(
                id=CaveatId.STABILITY_CUTOFF_OXIDE_CALIBRATED,
                subject=group.composition,
                source_ref=loaded.standing_caveats.get("stability_cutoff_oxide_calibrated"),
            )
        )
    if not enriched:
        flags.append(Flag.ENRICHMENT_MISSING)
        caveats.append(Caveat(id=CaveatId.ENRICHMENT_MISSING, subject=group.composition))
    for rv in pending_reference_values:
        if rv.composition == group.composition:
            caveats.append(
                Caveat(
                    id=CaveatId.REFERENCE_VALUE_PENDING,
                    subject=rv.entry_id,
                    source_ref=rv.provenance.source_record_id,
                )
            )
    if scored is None:
        exclusions.append(
            Exclusion(
                rule=ExclusionRule.DATA_NO_SCORABLE_CRITERIA,
                detail="no Materials Project polymorph with a hull energy",
                source_ref=None,
            )
        )
    total = None if exclusions else weighted_total(scores)
    if not exclusions and total is None:
        exclusions.append(
            Exclusion(
                rule=ExclusionRule.DATA_NO_SCORABLE_CRITERIA,
                detail="every weighted criterion is missing",
                source_ref=None,
            )
        )
    exclusions.sort(key=lambda e: EXCLUSION_ORDER.index(e.rule))
    breakdown = ScoreBreakdown(
        total=total,
        criteria=scores,
        band_gap_source=gap.source_used,
        band_gap_conflict=gap.conflict,
        hull_status_conflict=hull_conflict,
        ground_state_is_theoretical=group.ground_state_is_theoretical,
        near_cutoff=Flag.NEAR_CUTOFF in flags,
        dimensionality=dim,
        dimensionality_note=dim_note,
    )
    return Scored(
        composition=group.composition,
        group=group,
        polymorph=scored,
        breakdown=breakdown,
        exclusion=exclusions[0] if exclusions else None,
        flags=_ordered_flags(flags),
        caveats=_dedupe_caveats(caveats),
        other_exclusions=exclusions[1:],
    )


def _ordered_flags(flags: list[Flag]) -> list[Flag]:
    present = set(flags)
    return [f for f in Flag if f in present]


def _dedupe_caveats(caveats: list[Caveat]) -> list[Caveat]:
    seen: set[tuple[str, str | None]] = set()
    out: list[Caveat] = []
    for c in caveats:
        k = (c.id.value, c.subject)
        if k not in seen:
            seen.add(k)
            out.append(c)
    order = list(CaveatId)
    return sorted(out, key=lambda c: (order.index(c.id), c.subject or ""))


def _totals_under(weights: dict[str, float], rows: list[Scored]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:
        num = den = 0.0
        for s in r.breakdown.criteria:
            w = weights.get(s.criterion, 0.0)
            if w > 0 and not s.missing and s.normalized is not None:
                num += s.normalized * w
                den += w
        if den > 0:
            out[r.composition] = num / den
    return out


def _rank(rows: list[Scored], totals: dict[str, float]) -> dict[str, int]:
    ordered = sorted(
        (r for r in rows if r.composition in totals),
        key=lambda r: (
            -totals[r.composition],
            r.composition,
            r.polymorph.ids.mp or "" if r.polymorph else "",
        ),
    )
    return {r.composition: i + 1 for i, r in enumerate(ordered)}


def sensitivity(
    rows: list[Scored], weights: dict[str, float], perturbation: float
) -> dict[str, RankStability]:
    """Each weighted criterion is rescored at weight x(1 - p) and x(1 + p), one at a time.
    Perturbed weights are an analysis, not a setting, so site bounds do not clamp them."""
    base_rank = _rank(rows, _totals_under(weights, rows))
    ranks: dict[str, list[int]] = {c: [r] for c, r in base_rank.items()}
    perturbations = 0
    for c, w in sorted(weights.items()):
        if w <= 0:
            continue
        for factor in (1.0 - perturbation, 1.0 + perturbation):
            perturbations += 1
            alt = _rank(rows, _totals_under({**weights, c: w * factor}, rows))
            for comp, r in alt.items():
                ranks.setdefault(comp, []).append(r)
    return {
        comp: RankStability(
            rank_min=min(rs),
            rank_max=max(rs),
            rank_median=float(statistics.median(rs)),
            perturbations=perturbations,
            stable=min(rs) == max(rs),
        )
        for comp, rs in ranks.items()
    }


def thermo_enrichment_ids(
    rows: list[Scored],
    ranks: dict[str, int],
    *,
    top_k: int,
    cutoff_mev: float | None,
    band_mev: float | None,
    hull_key: str = MIXED_HULL,
) -> list[str]:
    """MP ids of every polymorph of the compositions ranked in the top K or whose scored hull
    lies within `band_mev` of the cutoff on either side. This is the id list the thermo
    adapter takes for per-functional hull documents."""
    chosen: set[str] = set()
    for r in rows:
        in_top = ranks.get(r.composition, 10**9) <= top_k
        near = False
        if r.polymorph is not None and cutoff_mev is not None and band_mev is not None:
            hull = r.polymorph.ground_state_energy(hull_key)
            near = hull is not None and abs(hull * 1000.0 - cutoff_mev) <= band_mev
        if in_top or near:
            chosen.update(p.ids.mp for p in r.group.polymorphs if p.ids.mp)
    return sorted(chosen)


def score_run(
    inputs: ScoringInputs,
    *,
    effective: EffectiveConfig,
    loaded: LoadedProfile,
    hazard_policy: HazardPolicy,
    site: SiteProfile,
    echa: tuple[str, str] | None,
    now: datetime | None = None,
    top_k: int | None = None,
) -> ScoringResult:
    now = now or datetime.now(UTC)
    profile = loaded.profile
    anchor_set = set(profile.anchors)
    # Per-run anchors (query.extra_anchors) get an anchor row and stay in the ranking.
    extra_anchors = set(effective.query.extra_anchors) - anchor_set
    cutoff = effective.stability_cutoff_mev
    scored_rows: list[Scored] = []
    anchor_rows: list[Scored] = []
    for group in sorted(inputs.groups, key=lambda g: g.composition):
        row = score_group(
            group,
            effective=effective,
            loaded=loaded,
            hazard_policy=hazard_policy,
            site=site,
            echa=echa,
            requested_mp=inputs.requested_polymorphs.get(group.composition),
            reference_values=inputs.reference_values,
            pending_reference_values=inputs.pending_reference_values,
            evidence_hits=inputs.evidence.get(group.composition),
        )
        (anchor_rows if group.composition in anchor_set else scored_rows).append(row)
        if group.composition in extra_anchors:
            anchor_rows.append(row)

    ranked_rows = [r for r in scored_rows if r.exclusion is None]
    ranked_rows.sort(key=lambda r: r.key)
    ranks = {r.composition: i + 1 for i, r in enumerate(ranked_rows)}
    stability = sensitivity(ranked_rows, effective.weights, profile.sensitivity_perturbation)

    def summary(r: Scored):  # type: ignore[no-untyped-def]
        return summarize_group(
            r.group,
            scored=r.polymorph,
            cutoff_mev=cutoff,
            reference_values=[
                *(v for v in inputs.reference_values if v.composition == r.composition),
                *(v for v in inputs.pending_reference_values if v.composition == r.composition),
            ],
        )

    candidates = [
        Candidate(
            composition=r.composition,
            group=summary(r),
            score=r.breakdown,
            rank=ranks.get(r.composition),
            excluded=r.exclusion,
            flags=r.flags,
            caveats=r.caveats,
            sensitivity=stability.get(r.composition),
            rationale_slot=f"candidate:{r.composition}:one_line",
        )
        for r in scored_rows
    ]
    anchors = []
    for r in anchor_rows:
        would = None
        if r.exclusion is None:
            would = 1 + sum(1 for c in ranked_rows if c.key < r.key)
        anchors.append(
            Anchor(
                composition=r.composition,
                group=summary(r),
                score=r.breakdown,
                would_rank=would,
                out_of=len(ranked_rows),
                excluded=r.exclusion,
                flags=r.flags,
                caveats=r.caveats,
            )
        )
    missing = [
        MissingPropertyMarker(
            property=item.lower().replace(" ", "_").replace("'", ""),
            text=item,
            source_entry=SITE_PROFILE_REF,
        )
        for item in site.screen_cannot_tell_you
    ]
    k = top_k if top_k is not None else effective.top_n
    thermo_ids = thermo_enrichment_ids(
        scored_rows + anchor_rows,
        ranks,
        top_k=k,
        cutoff_mev=cutoff,
        band_mev=profile.stability.near_cutoff_band_mev_per_atom,
    )
    log = [
        DecisionLogEntry(
            at=now,
            actor="scorer",
            step="score",
            summary=(
                f"{len(ranked_rows)} ranked, {len(scored_rows) - len(ranked_rows)} excluded, "
                f"{len(anchor_rows)} anchors; profile {profile.name} v{profile.version}"
            ),
            detail={
                "weights": dict(effective.weights),
                "band_gap_policy": profile.band_gap.policy.value,
                "excluded": {
                    r.composition: r.exclusion.rule.value for r in scored_rows if r.exclusion
                },
                "also_excluded_by": {
                    r.composition: [e.rule.value for e in r.other_exclusions]
                    for r in scored_rows
                    if r.other_exclusions
                },
                "profile_notes": list(loaded.notes),
            },
        ),
        DecisionLogEntry(
            at=now,
            actor="scorer",
            step="sensitivity",
            summary=(
                f"weights perturbed by +/-{profile.sensitivity_perturbation:g}; "
                f"{sum(1 for s in stability.values() if not s.stable)} of {len(stability)} "
                "ranked candidates move"
            ),
        ),
        DecisionLogEntry(
            at=now,
            actor="scorer",
            step="thermo_enrichment",
            summary=f"{len(thermo_ids)} MP ids selected for per-functional thermo documents",
            detail={"top_k": k, "ids": thermo_ids},
        ),
    ]
    return ScoringResult(
        candidates=candidates,
        anchors=anchors,
        missing_properties=missing,
        decision_log=log,
        thermo_enrichment_ids=thermo_ids,
        notes=list(loaded.notes),
    )
