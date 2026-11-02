"""Build fixtures/bundles/sample_bundle.json from recorded data for the 11 baseline oxides.

Groups, provenance, hazards, gaps, and literature are real (replayed from cassettes with no
network). Scores are ILLUSTRATIVE placeholders so Tracks B, C, and E can build against a
valid bundle before Track A's scorer merges; the run metadata says so. Hazard exclusions do
follow the entered rules in config/hazard_policy.yaml (ThO2 radioactive, BeO IARC Group 1).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import yaml

from materials_triage.adapters import expt_gap, jarvis, mp, openalex, pubchem
from materials_triage.adapters.common import reduced_formula
from materials_triage.adapters.recording import ADAPTER_CASSETTES, ROOT, make_vcr
from materials_triage.adapters.transport import TIMEOUT, USER_AGENT, HttpxTransport
from materials_triage.config.schema import (
    CoreConfig,
    QuerySettings,
    default_paths,
    resolve,
    scoring_profile_from_yaml,
    site_profile_from_yaml,
)
from materials_triage.records import CompositionGroup, LiteratureSearchResult
from materials_triage.records.bundle import (
    Anchor,
    Candidate,
    Caveat,
    CaveatId,
    ConfirmedCriteria,
    CriterionScore,
    DecisionLogEntry,
    EvidenceHit,
    EvidenceLabel,
    Exclusion,
    ExclusionRule,
    FetchMode,
    Flag,
    MissingPropertyMarker,
    ProvenanceBundle,
    RankStability,
    RationaleSlot,
    RunMetadata,
    ScoreBreakdown,
    VerifierFailure,
    VerifierReport,
)
from materials_triage.records.groups import build_group, merge_matches
from materials_triage.scoring.polymorphs import summarize_group
from materials_triage.settings import Settings

OUT = ROOT / "fixtures" / "bundles" / "sample_bundle.json"
SNAPSHOTS = ROOT / "fixtures" / "snapshots"
VCR = make_vcr("none")
SAMPLE_RUN_ID = UUID("00000000-0000-4000-8000-000000000001")
FIXED_TIME = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def cassette(source: str, name: str):  # type: ignore[no-untyped-def]
    return VCR.use_cassette(str(ADAPTER_CASSETTES / source / f"{name}.yaml"))


def main() -> int:
    spec = yaml.safe_load((ROOT / "fixtures" / "compositions.yaml").read_text())
    manifest = json.loads((SNAPSHOTS / "MANIFEST.json").read_text())["snapshots"]
    hazard_policy = yaml.safe_load((ROOT / "config" / "hazard_policy.yaml").read_text())
    settings = Settings(_env_file=None, mp_api_key="recorded", openalex_api_key="recorded")  # type: ignore[call-arg]
    transport = HttpxTransport(
        settings,
        client=httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}),
        sleep=lambda _s: None,
    )

    jv_raw = jarvis.load_slice(
        SNAPSHOTS / "jarvis_dft_3d.slice.json",
        full_file_sha256=manifest["jarvis_dft_3d"]["sha256"],
        fetched_at=FIXED_TIME,
    )
    jv_polys = jarvis.polymorphs(jarvis.records(jv_raw))
    gap_raw = expt_gap.load_slice(
        SNAPSHOTS / "expt_gap.slice.json",
        table="expt_gap",
        file_sha256=manifest["expt_gap"]["sha256"],
        fetched_at=FIXED_TIME,
    )
    gap_aggs = expt_gap.aggregates(expt_gap.records(gap_raw)[0])

    radioactive = set(hazard_policy["tiers"]["radioactive_exclude"]["elements"])
    exclude_elements = {
        e["element"]: e
        for e in hazard_policy["tiers"]["exclude"]["entries"]
        if e["status"] == "entered"
    }

    groups: dict[str, CompositionGroup] = {}
    hazards = {}
    literature: dict[str, LiteratureSearchResult] = {}
    conflicts: dict[str, bool] = {}
    for display in spec["groups"]["baseline_oxides"]:
        key = reduced_formula(display)
        with cassette("mp", f"summary_{key}"):
            summary = mp.summary_records(transport.get(mp.plan_summary_by_formula(key)))
        ids = [s.source_record_id for s in summary]
        with cassette("mp", f"thermo_{key}"):
            thermo = [r for c in mp.plan_thermo(ids) for r in mp.thermo_records(transport.get(c))]
        with cassette("mp", f"dielectric_{key}"):
            diel = [
                r for c in mp.plan_dielectric(ids) for r in mp.dielectric_records(transport.get(c))
            ]
        assembly = mp.assemble(summary, thermo, diel)
        merged = merge_matches(assembly.polymorphs, [p for p in jv_polys if p.composition == key])
        name = spec["common_names"][display]
        with cassette("pubchem", display):
            by_name = transport.get(pubchem.plan_cids_by_name(name))
            by_formula = transport.get(pubchem.plan_cids_by_formula(display))
            cid, _ = pubchem.choose_cid(pubchem.cids(by_name), pubchem.cids(by_formula))
            ghs = transport.get(pubchem.plan_ghs(cid)) if cid else None
            syn = transport.get(pubchem.plan_synonyms(cid)) if cid else None
        hazards[key] = pubchem.hazard(key, by_name=by_name, by_formula=by_formula, ghs=ghs, syn=syn)
        q = f"{display} thin film"
        with cassette("openalex", key):
            res = openalex.result(
                transport.get(openalex.plan_search(q)),
                transport.get(openalex.plan_count(q)),
                composition=key,
                query=q,
                scope="title_and_abstract",
            )
        literature[key] = res
        groups[key] = build_group(
            key, merged, experimental_gaps=gap_aggs.get(key), hazard=hazards[key], literature=res
        )
        conflicts[key] = any(p.hull_status_conflict for p in merged)

    paths = default_paths()
    profile, notes = scoring_profile_from_yaml(paths["scoring_profile"])
    site = site_profile_from_yaml(paths["site_profile"])
    query = QuerySettings(
        profile=profile.name, mode="candidate_list", candidate_list=list(groups), top_n=10
    )
    effective, clamps = resolve(CoreConfig(), site, profile, query)

    def elements(comp: str) -> set[str]:
        from pymatgen.core.composition import Composition

        return {e.symbol for e in Composition(comp).elements}

    def ground(g: CompositionGroup):  # type: ignore[no-untyped-def]
        return next(p for p in g.polymorphs if p.ids.mp == g.ground_state_mp)

    candidates: list[Candidate] = []
    anchors: list[Anchor] = []
    scored: list[tuple[float, str]] = []
    for key, g in groups.items():
        gs = ground(g)
        els = elements(key)
        excluded = None
        if els & radioactive:
            excluded = Exclusion(
                rule=ExclusionRule.HAZARD_RADIOACTIVE,
                detail=f"{sorted(els & radioactive)} has no stable isotope",
                source_ref="config/hazard_policy.yaml#tiers.radioactive_exclude",
            )
        elif els & set(exclude_elements):
            el = sorted(els & set(exclude_elements))[0]
            excluded = Exclusion(
                rule=ExclusionRule.HAZARD_EXCLUDE,
                detail=exclude_elements[el]["reason"],
                source_ref=f"config/hazard_policy.yaml#tiers.exclude.{el}",
            )
        hull = gs.hull_energy[mp.MIXED_HULL].value
        gap_val = gs.band_gap["mp_summary"].value
        tbmbj = gs.band_gap.get("jarvis_tbmbj")
        expt = g.experimental_gaps.median if g.experimental_gaps else None
        if expt is not None:
            gap_used, gap_src = expt, "experimental_median"
        elif tbmbj is not None and tbmbj.value is not None:
            gap_used, gap_src = tbmbj.value, "tbmbj"
        else:
            gap_used, gap_src = gap_val, "pbe"
        # ILLUSTRATIVE normalizations; Track A replaces these.
        stab_n = None if hull is None else max(0.0, min(1.0, 1 - (hull * 1000) / 94))
        gap_n = None if gap_used is None else max(0.0, min(1.0, gap_used / 5.0))
        simp_n = 1.0 if len(els) <= 2 else 0.5
        ev_n = min(1.0, len(literature[key].hits) / 5)
        crit = [
            CriterionScore(
                criterion="stability",
                raw_value=hull,
                raw_unit="eV/atom",
                source=mp.MIXED_HULL,
                normalized=stab_n,
                weight=effective.weights["stability"],
                contribution=(stab_n or 0.0) * effective.weights["stability"],
                missing=hull is None,
            ),
            CriterionScore(
                criterion="band_gap",
                raw_value=gap_used,
                raw_unit="eV",
                source=gap_src,
                normalized=gap_n,
                weight=effective.weights["band_gap"],
                contribution=(gap_n or 0.0) * effective.weights["band_gap"],
                missing=gap_used is None,
            ),
            CriterionScore(
                criterion="hazard",
                raw_value=None,
                raw_unit=None,
                source="config/hazard_policy.yaml",
                normalized=1.0 if excluded is None else 0.0,
                weight=effective.weights["hazard"],
                contribution=effective.weights["hazard"] if excluded is None else 0.0,
                missing=False,
                notes=[
                    f"GHS codes in {hazards[key].notifications_total or 0} notifications: "
                    f"{hazards[key].h_codes}"
                ],
            ),
            CriterionScore(
                criterion="simplicity",
                raw_value=float(len(els)),
                raw_unit="elements",
                source="composition",
                normalized=simp_n,
                weight=effective.weights["simplicity"],
                contribution=simp_n * effective.weights["simplicity"],
                missing=False,
            ),
            CriterionScore(
                criterion="evidence",
                raw_value=float(len(literature[key].hits)),
                raw_unit="abstracts",
                source="openalex",
                normalized=ev_n,
                weight=effective.weights["evidence"],
                contribution=ev_n * effective.weights["evidence"],
                missing=False,
            ),
            CriterionScore(
                criterion="dielectric_constant",
                raw_value=gs.dielectric["e_total"].value,
                raw_unit="1",
                source="mp_dfpt",
                normalized=None,
                weight=0.0,
                contribution=0.0,
                missing=gs.dielectric["e_total"].value is None,
                missing_reason=str(gs.dielectric["e_total"].missing_reason)
                if gs.dielectric["e_total"].value is None
                else None,
            ),
        ]
        total = (
            None
            if excluded
            else round(
                sum(c.contribution for c in crit) / max(1e-9, sum(c.weight for c in crit)), 4
            )
        )
        gap_conflict = bool(
            expt is not None
            and tbmbj is not None
            and tbmbj.value is not None
            and abs(expt - tbmbj.value) > 1.0
        )
        breakdown = ScoreBreakdown(
            total=total,
            criteria=crit,
            band_gap_source=gap_src,
            band_gap_conflict=gap_conflict,
            hull_status_conflict=conflicts[key],
            ground_state_is_theoretical=g.ground_state_is_theoretical,
            near_cutoff=bool(hull is not None and 0.070 <= hull <= 0.094),
        )
        flags = [
            f
            for f, on in (
                (Flag.HULL_STATUS_CONFLICT, conflicts[key]),
                (Flag.BAND_GAP_CONFLICT, gap_conflict),
                (Flag.GROUND_STATE_IS_THEORETICAL, bool(g.ground_state_is_theoretical)),
            )
            if on
        ]
        summary = summarize_group(g, scored=gs, cutoff_mev=94.0)
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
                rationale_slot=f"candidate:{key}:one_line",
            )
        )
        if total is not None:
            scored.append((total, key))
    scored.sort(key=lambda t: (-t[0], t[1]))
    rank_of = {k: i + 1 for i, (_, k) in enumerate(scored)}
    for c in candidates:
        c.rank = rank_of.get(c.composition)
        if c.rank is not None:
            c.sensitivity = RankStability(
                rank_min=max(1, c.rank - 1),
                rank_max=min(len(scored), c.rank + 1),
                rank_median=float(c.rank),
                perturbations=12,
                stable=True,
            )
    for a in anchors:
        a.out_of = len(scored)
        a.would_rank = (
            (
                1
                + sum(
                    1
                    for t, _ in scored
                    if a.score and a.score.total is not None and t > a.score.total
                )
            )
            if a.score and a.score.total is not None
            else None
        )

    hf_hits = literature["HfO2"].hits
    verified_sentence = (hf_hits[0].abstract_text or "").split(". ")[0] + "."
    evidence = [
        EvidenceHit(
            composition="HfO2",
            openalex_id=hf_hits[0].openalex_id,
            label=EvidenceLabel.THIN_FILM_DEPOSITED,
            deposition_method=None,
            supporting_sentence=verified_sentence,
            verified=True,
            provenance=hf_hits[0].provenance,
        ),
        EvidenceHit(
            composition="HfO2",
            openalex_id=hf_hits[1].openalex_id,
            label=EvidenceLabel.DIELECTRIC_CHARACTERIZED,
            deposition_method=None,
            supporting_sentence=(
                "This sentence does not appear in the abstract and was planted to show a "
                "failed quote check."
            ),
            verified=False,
            verifier_note="quote not found verbatim in stored abstract",
            provenance=hf_hits[1].provenance,
        ),
    ]
    missing = [
        MissingPropertyMarker(
            property=item.lower().replace(" ", "_"),
            text=item,
            source_entry="config/site_profile.default.yaml#screen_cannot_tell_you",
        )
        for item in site.screen_cannot_tell_you
    ]
    rationale = {
        c.rationale_slot: RationaleSlot(
            slot=c.rationale_slot,
            text=(
                f"{{formula:{c.composition}}} ranks {{rank:{c.composition}}} on "
                "{criterion:stability} and {criterion:band_gap}; see caveats."
            ),
            verified=True,
        )
        for c in candidates
        if c.rationale_slot and c.rank
    }
    bundle = ProvenanceBundle(
        run=RunMetadata(
            run_id=SAMPLE_RUN_ID,
            started_at=FIXED_TIME,
            finished_at=FIXED_TIME,
            config_sha=effective.config_sha,
            profile_name=profile.name,
            profile_version=profile.version,
            policy_version=str(hazard_policy.get("schema_version", 0)),
            prompt_hash=None,
            model_version=None,
            provider=None,
            source_versions={
                "materials_project": "2026.09.28",
                "jarvis_dft_3d": manifest["jarvis_dft_3d"]["sha256"][:12],
                "expt_gap": manifest["expt_gap"]["sha256"][:12],
            },
            fetch_mode=FetchMode.REPLAY,
            partial=False,
            note=(
                "SAMPLE BUNDLE: groups, provenance, hazards, gaps, and literature are real "
                "recorded data; score normalizations are illustrative placeholders, not Track A "
                "scoring. Scoring profile notes: " + "; ".join(notes)
            ),
        ),
        criteria=ConfirmedCriteria(
            request_text="Rank the eleven baseline oxides as thin-film dielectric candidates.",
            parsed_by="criteria_file",
            confirmed_at=FIXED_TIME,
            mode="candidate_list",
            candidate_list=list(groups),
            effective_settings=query.model_dump(mode="json"),
            clamps=[],
            defaults_applied=["verbosity=standard", "view=pi_summary"],
        ),
        candidates=candidates,
        anchors=anchors,
        evidence=evidence,
        missing_properties=missing,
        decision_log=[
            DecisionLogEntry(
                at=FIXED_TIME,
                actor="pipeline",
                step="build_sample",
                summary="sample bundle generated from recorded cassettes with illustrative scores",
            )
        ],
        rationale=rationale,
        verifier=VerifierReport(
            checked_slots=len(rationale),
            checked_evidence=len(evidence),
            failures=[
                VerifierFailure(
                    kind="quote_mismatch",
                    location=f"evidence:{hf_hits[1].openalex_id}",
                    fragment=evidence[1].supporting_sentence or "",
                    action="hit_dropped",
                )
            ],
            passed=False,
        ),
        availability_events=[],
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(bundle.model_dump_json(indent=1) + "\n")
    ranked = [
        (c.rank, c.composition, c.score.total if c.score else None)
        for c in sorted(candidates, key=lambda c: c.rank or 99)
    ]
    print("ranked:", ranked)
    print("excluded:", [(c.composition, c.excluded.rule) for c in candidates if c.excluded])
    print("anchors:", [(a.composition, a.would_rank, a.out_of) for a in anchors])
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
