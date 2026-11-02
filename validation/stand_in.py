"""TEMPORARY stand-in scorer so the validation path runs end to end before Track A's scorer
merges. It reproduces the ILLUSTRATIVE normalizations of scripts/build_sample_bundle.py over
any composition list and emits the Track A vocabularies. Nothing it produces is reported as a
result; the run note says so. Deleted when Track A's `scoring.scorer` lands.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import yaml
from pymatgen.core.composition import Composition

from materials_triage.config.schema import (
    CoreConfig,
    QuerySettings,
    default_paths,
    resolve,
    scoring_profile_from_yaml,
    site_profile_from_yaml,
)
from materials_triage.records.bundle import (
    Anchor,
    Candidate,
    Caveat,
    CaveatId,
    ConfirmedCriteria,
    CriterionScore,
    DecisionLogEntry,
    Exclusion,
    ExclusionRule,
    FetchMode,
    Flag,
    ProvenanceBundle,
    RunMetadata,
    ScoreBreakdown,
)
from materials_triage.scoring.polymorphs import MIXED_HULL, select_scored, summarize_group
from validation.groups import LoadedGroup

STAND_IN_RUN_ID = UUID("00000000-0000-4000-8000-00000000000e")
FIXED_TIME = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
NOTE = "STAND-IN SCORER (Track E, temporary): illustrative normalizations, not Track A scoring."


def _elements(composition: str) -> set[str]:
    return {e.symbol for e in Composition(composition).elements}


def _hazard_tiers(policy: dict[str, Any]) -> tuple[set[str], dict[str, str], set[str], set[str]]:
    tiers = policy["tiers"]
    radioactive = set(tiers["radioactive_exclude"]["elements"])
    exclude = {e["element"]: str(e["reason"]) for e in tiers["exclude"]["entries"]}
    acute_exclude = {
        e["element"] for e in tiers["acute_toxicity"]["element_tiers"] if e["tier"] == "exclude"
    }
    flag = {e["element"] for e in tiers["flag"]["entries"]} | {
        e["element"] for e in tiers["acute_toxicity"]["element_tiers"] if e["tier"] == "flag"
    }
    return radioactive, exclude, acute_exclude, flag


def score_stand_in(
    groups: dict[str, LoadedGroup], *, request_text: str = "validation stand-in"
) -> ProvenanceBundle:
    paths = default_paths()
    profile, notes = scoring_profile_from_yaml(paths["scoring_profile"])
    site = site_profile_from_yaml(paths["site_profile"])
    policy = yaml.safe_load(paths["hazard_policy"].read_text())
    radioactive, exclude, acute_exclude, flag_elements = _hazard_tiers(policy)
    query = QuerySettings(
        profile=profile.name, mode="candidate_list", candidate_list=sorted(groups), top_n=50
    )
    effective, clamps = resolve(CoreConfig(), site, profile, query)
    cutoff = profile.stability.cutoff_mev_per_atom or 94.0

    candidates: list[Candidate] = []
    anchors: list[Anchor] = []
    scored_totals: list[tuple[float, str]] = []
    for key, lg in sorted(groups.items()):
        g = lg.group
        gs = select_scored(g)
        els = _elements(key)
        excluded: Exclusion | None = None
        flags: list[Flag] = []
        if els & radioactive:
            excluded = Exclusion(
                rule=ExclusionRule.HAZARD_RADIOACTIVE,
                detail=f"{sorted(els & radioactive)} has no stable isotope",
                source_ref="config/hazard_policy.yaml#tiers.radioactive_exclude",
            )
        elif els & set(exclude):
            el = sorted(els & set(exclude))[0]
            excluded = Exclusion(
                rule=ExclusionRule.HAZARD_EXCLUDE,
                detail=exclude[el],
                source_ref=f"config/hazard_policy.yaml#tiers.exclude.{el}",
            )
        elif els & acute_exclude:
            el = sorted(els & acute_exclude)[0]
            excluded = Exclusion(
                rule=ExclusionRule.HAZARD_ACUTE_ELEMENT,
                detail=f"{el} representative compound meets the acute toxicity exclude set",
                source_ref=f"config/hazard_policy.yaml#tiers.acute_toxicity.element_tiers.{el}",
            )
        hull = None if gs is None else gs.ground_state_energy(MIXED_HULL)
        if excluded is None and hull is not None and hull * 1000 > cutoff:
            excluded = Exclusion(
                rule=ExclusionRule.STABILITY_CUTOFF,
                detail=f"{hull * 1000:.0f} meV/atom above the {cutoff:.0f} meV/atom cutoff",
                source_ref="config/scoring_profiles#criteria.stability.cutoff_mev_per_atom",
            )
        if excluded is None and len(els) > profile.simplicity.max_elements:
            excluded = Exclusion(
                rule=ExclusionRule.SIMPLICITY_MAX_ELEMENTS,
                detail=f"{len(els)} elements, limit {profile.simplicity.max_elements}",
                source_ref="config/scoring_profiles#criteria.simplicity.max_elements",
            )
        if els & flag_elements:
            flags.append(Flag.HAZARD_FLAG)
        if g.hazard is None:
            flags.append(Flag.HAZARD_UNKNOWN)
        if lg.hull_status_conflict:
            flags.append(Flag.HULL_STATUS_CONFLICT)
        if g.ground_state_is_theoretical:
            flags.append(Flag.GROUND_STATE_IS_THEORETICAL)

        tbmbj = None if gs is None else gs.band_gap.get("jarvis_tbmbj")
        pbe = None if gs is None else gs.band_gap.get("mp_summary")
        expt = g.experimental_gaps.median if g.experimental_gaps else None
        if expt is not None:
            gap_used, gap_src = expt, "experimental_median"
        elif tbmbj is not None and tbmbj.value is not None:
            gap_used, gap_src = tbmbj.value, "tbmbj"
        elif pbe is not None and pbe.value is not None:
            gap_used, gap_src = pbe.value, "pbe"
        else:
            gap_used, gap_src = None, None
        gap_conflict = bool(
            expt is not None
            and tbmbj is not None
            and tbmbj.value is not None
            and abs(expt - tbmbj.value) > 1.0
        )
        if gap_conflict:
            flags.append(Flag.BAND_GAP_CONFLICT)
        stab_n = None if hull is None else max(0.0, min(1.0, 1 - (hull * 1000) / cutoff))
        gap_n = None if gap_used is None else max(0.0, min(1.0, gap_used / 5.0))
        simp_n = 1.0 if len(els) <= 2 else 0.5
        hits = 0 if g.literature is None else len(g.literature.hits)
        ev_n = min(1.0, hits / 5)
        haz_n = 0.5 if g.hazard is None else 1.0
        w = effective.weights
        crit = [
            CriterionScore(
                criterion="stability",
                raw_value=hull,
                raw_unit="eV/atom",
                source=MIXED_HULL,
                normalized=stab_n,
                weight=w["stability"],
                contribution=(stab_n or 0.0) * w["stability"],
                missing=hull is None,
            ),
            CriterionScore(
                criterion="band_gap",
                raw_value=gap_used,
                raw_unit="eV",
                source=gap_src,
                normalized=gap_n,
                weight=w["band_gap"],
                contribution=(gap_n or 0.0) * w["band_gap"],
                missing=gap_used is None,
            ),
            CriterionScore(
                criterion="hazard",
                raw_value=None,
                raw_unit=None,
                source="config/hazard_policy.yaml",
                normalized=haz_n,
                weight=w["hazard"],
                contribution=haz_n * w["hazard"],
                missing=False,
            ),
            CriterionScore(
                criterion="simplicity",
                raw_value=float(len(els)),
                raw_unit="elements",
                source="composition",
                normalized=simp_n,
                weight=w["simplicity"],
                contribution=simp_n * w["simplicity"],
                missing=False,
            ),
            CriterionScore(
                criterion="evidence",
                raw_value=float(hits),
                raw_unit="abstracts",
                source="openalex",
                normalized=ev_n,
                weight=w["evidence"],
                contribution=ev_n * w["evidence"],
                missing=False,
            ),
        ]
        present_weight = sum(c.weight for c in crit if not c.missing)
        total = (
            None
            if excluded is not None or present_weight == 0
            else round(sum(c.contribution for c in crit) / present_weight, 4)
        )
        breakdown = ScoreBreakdown(
            total=total,
            criteria=crit,
            band_gap_source=gap_src,
            band_gap_conflict=gap_conflict,
            hull_status_conflict=lg.hull_status_conflict,
            ground_state_is_theoretical=g.ground_state_is_theoretical,
        )
        summary = summarize_group(g, scored=gs, cutoff_mev=cutoff)
        if key in profile.anchors:
            anchors.append(
                Anchor(composition=key, group=summary, score=breakdown, would_rank=None, out_of=0)
            )
            continue
        candidates.append(
            Candidate(
                composition=key,
                group=summary,
                score=breakdown,
                rank=None,
                excluded=excluded,
                flags=flags,
                caveats=[Caveat(id=CaveatId.BAND_OFFSETS_NOT_CHECKED)],
            )
        )
        if total is not None:
            scored_totals.append((total, key))
    scored_totals.sort(key=lambda t: (-t[0], t[1]))
    rank_of = {k: i + 1 for i, (_, k) in enumerate(scored_totals)}
    for c in candidates:
        c.rank = rank_of.get(c.composition)
    for a in anchors:
        a.out_of = len(scored_totals)
        if a.score and a.score.total is not None:
            t = a.score.total
            a.would_rank = 1 + sum(1 for s, _ in scored_totals if s > t)
    return ProvenanceBundle(
        run=RunMetadata(
            run_id=STAND_IN_RUN_ID,
            started_at=FIXED_TIME,
            finished_at=FIXED_TIME,
            config_sha=effective.config_sha,
            profile_name=profile.name,
            profile_version=profile.version,
            policy_version=str(policy.get("schema_version", 0)),
            prompt_hash=None,
            model_version=None,
            provider=None,
            source_versions={},
            fetch_mode=FetchMode.REPLAY,
            partial=False,
            note=NOTE + " Profile notes: " + "; ".join(notes),
        ),
        criteria=ConfirmedCriteria(
            request_text=request_text,
            parsed_by="criteria_file",
            confirmed_at=FIXED_TIME,
            mode="candidate_list",
            candidate_list=sorted(groups),
            effective_settings=query.model_dump(mode="json"),
            clamps=[],
        ),
        candidates=candidates,
        anchors=anchors,
        decision_log=[
            DecisionLogEntry(at=FIXED_TIME, actor="scorer", step="stand_in", summary=NOTE)
        ],
    )
