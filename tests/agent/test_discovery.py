"""Discovery mode over the recorded dielectric discovery cassette (PBE gap floor 3.0 eV,
hull up to 94 meV/atom): paged in full, scored on summary data, the top K enriched, and
refused above the ceiling. The scorer here is a
test-only stand-in that ranks by the summary band gap; Track A's replaces it."""

from __future__ import annotations

from pathlib import Path

import pytest

from materials_triage.adapters import mp
from materials_triage.adapters.base import Call, RawResponse
from materials_triage.agent import parse, pipeline
from materials_triage.agent.scoring_port import ScoredSet, ScoreRequest
from materials_triage.config import schema as cs
from materials_triage.records.bundle import Anchor, Candidate, CriterionScore, ScoreBreakdown
from materials_triage.scoring.polymorphs import select_scored, summarize_group
from tests.agent.test_pipeline import CassetteTransport

Layers = tuple[cs.CoreConfig, cs.SiteProfile, cs.ScoringProfile]
ROOT = Path(__file__).resolve().parents[2]


class DiscoveryCassettes(CassetteTransport):
    """The pipeline cassettes plus the discovery pages (excluded by the base class)."""

    def __init__(self) -> None:
        super().__init__()
        from scripts.seed_store_from_cassettes import iter_raw

        for path, raw in iter_raw(ROOT / "fixtures" / "adapters" / "mp"):
            if "discovery" in path.name:
                self.by_key.setdefault(raw.call.cache_key, raw)


def gap_scorer(request: ScoreRequest) -> ScoredSet:
    """Rank by the scored polymorph's summary band gap, descending; ties by composition."""
    rows: list[tuple[float, str, Candidate]] = []
    anchors: list[Anchor] = []
    for comp, group in request.groups.items():
        scored = select_scored(group)
        summary = summarize_group(group, scored=scored, cutoff_mev=94.0)
        gap = scored.band_gap.get("mp_summary") if scored else None
        value = gap.value if gap is not None else None
        breakdown = ScoreBreakdown(
            total=value,
            criteria=[
                CriterionScore(
                    criterion="band_gap",
                    raw_value=value,
                    raw_unit="eV",
                    source="pbe",
                    normalized=None,
                    weight=1.0,
                    contribution=value or 0.0,
                    missing=value is None,
                )
            ],
            band_gap_source="pbe",
        )
        if comp in request.profile.anchors:
            anchors.append(
                Anchor(composition=comp, group=summary, score=breakdown, would_rank=None, out_of=0)
            )
            continue
        rows.append(
            (
                -(value or 0.0),
                comp,
                Candidate(
                    composition=comp, group=summary, score=breakdown, rank=None, excluded=None
                ),
            )
        )
    rows.sort(key=lambda t: (t[0], t[1]))
    for i, (_, _, c) in enumerate(rows, start=1):
        c.rank = i
    for a in anchors:
        a.out_of = len(rows)
    return ScoredSet(candidates=[c for _, _, c in rows], anchors=anchors, note="test gap scorer")


@pytest.fixture(scope="module")
def transport() -> DiscoveryCassettes:
    return DiscoveryCassettes()


@pytest.fixture(scope="module")
def sources() -> pipeline.Sources:
    return pipeline.Sources.load()


def _inputs(layers: Layers, tmp_path: Path, **settings: object) -> pipeline.RunInputs:
    core, site, profile = layers
    path = tmp_path / "criteria.yaml"
    lines = ["mode: discovery"] + [f"{k}: {v}" for k, v in settings.items()]
    path.write_text("\n".join(lines) + "\n")
    outcome = parse.parse_from_file(
        path, core=core, site=site, profile=profile, cli_profile=profile.name
    )
    return pipeline.RunInputs(
        request_text="oxides with a gap between two and three electronvolts",
        parse=outcome,
        core=core,
        site=site,
        profile=profile,
        hazard_policy={},
    )


def test_discovery_filter_sends_only_hard_rules_at_their_loosest_value(layers: Layers) -> None:
    """The prefilter principle: the soft preference (5 eV) and the query's tighter window and
    cutoff never reach the API; the floor is discovery_pbe_floor_ev and the hull limit is the
    site maximum, so excluded rows stay fetched for relaxation counts."""
    _, site, profile = layers
    assert profile.band_gap.soft_preference_start_ev == 5.0
    f = pipeline.discovery_filter(
        cs.QuerySettings(
            profile=profile.name,
            mode="discovery",
            band_gap_min_ev=9.0,
            band_gap_max_ev=10.0,
            e_above_hull_max_mev=0.0,
        ),
        profile,
        site,
    )
    assert f.params() == {
        "elements": "O",
        "nelements_min": "2",
        "nelements_max": "3",
        "band_gap_min": "3.0",
        "energy_above_hull_min": "0.0",
        "energy_above_hull_max": "0.094",
    }


def test_discovery_pages_everything_scores_summaries_and_enriches_the_top_k(
    layers: Layers, tmp_path: Path, transport: DiscoveryCassettes, sources: pipeline.Sources
) -> None:
    inputs = _inputs(layers, tmp_path, band_gap_min_ev=2.0, band_gap_max_ev=3.0, top_n=3)
    bundle = pipeline.run(inputs, fetch=transport, sources=sources, scorer=gap_scorer)
    steps = [d.step for d in bundle.decision_log]
    assert steps[:3] == ["start", "discovery", "enrich"] and steps[-1] == "verify"
    assert "classify" in steps and "score" in steps
    discovery = next(d for d in bundle.decision_log if d.step == "discovery")
    assert discovery.detail["total"] == 3748 and "3748 summary documents" in discovery.summary
    assert "band_gap_max" not in discovery.detail["params"]  # the query window stays in code
    assert len(bundle.candidates) > 1000 and bundle.criteria.mode == "discovery"
    ranked = bundle.ranked()
    gaps = [c.score.total for c in ranked if c.score]
    assert gaps == sorted(gaps, reverse=True) and gaps[0] is not None
    enrich = next(d for d in bundle.decision_log if d.step == "enrich")
    assert enrich.summary.startswith("round 1: cross-checks fetched for")
    assert enrich.summary.endswith("of 4 candidates")  # top 3 plus the SiO2 anchor
    assert [a.composition for a in bundle.anchors] == ["SiO2"]
    si = bundle.anchors[0]
    assert si.group.hazard is not None and si.group.literature is not None
    top = ranked[:3]
    unrecorded = [c.composition for c in top if c.group.literature is None]
    assert all(f"{c}: enrichment unavailable" in bundle.run.partial_reasons for c in unrecorded)
    assert bundle.run.partial is (len(unrecorded) > 0 or bool(bundle.availability_events))
    assert bundle.verifier is not None and bundle.verifier.passed


def test_discovery_above_the_ceiling_is_refused_with_the_count(
    layers: Layers, tmp_path: Path, sources: pipeline.Sources, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mp, "DISCOVERY_CEILING", 10)

    def fetch(call: Call) -> RawResponse | None:
        if call.endpoint == "heartbeat":
            return None
        body = b'{"data": [], "meta": {"total_doc": 11}}'
        return RawResponse(
            call=call,
            status=200,
            body=body,
            content_type="application/json",
            fetched_at=RawResponse.now(),
        )

    inputs = _inputs(layers, tmp_path, band_gap_min_ev=2.0)
    bundle = pipeline.run(inputs, fetch=fetch, sources=sources, scorer=gap_scorer)
    assert bundle.candidates == [] and bundle.run.partial is True
    assert any("above the ceiling of 10; narrow the query" in r for r in bundle.run.partial_reasons)
    refused = next(d for d in bundle.decision_log if d.step == "discovery")
    assert refused.detail == {"total": 11, "ceiling": 10}


@pytest.mark.parametrize(
    ("profile_name", "total", "request_text"),
    [
        ("oxide_dielectric_thin_film", 3748, "wide gap oxide dielectrics"),
        ("oxide_photocatalyst", 3082, "visible light oxide photocatalysts"),
    ],
)
def test_recorded_discovery_queries_run_offline_end_to_end_with_the_real_scorer(
    profile_name: str,
    total: int,
    request_text: str,
    tmp_path: Path,
    transport: DiscoveryCassettes,
    sources: pipeline.Sources,
) -> None:
    """Owner request, Nov 3: the dielectric profile's default discovery (PBE floor 3.0 eV,
    Track F) and the photocatalyst window (2.0 to 3.3 eV) both page
    from cassettes, and every composition in the final top 10 carries the full cross-checks
    because the enrich-classify-score loop repeats until the top K is enriched."""
    from materials_triage.agent.scoring_port import default_scorer, track_a_scorer

    track_a_scorer()  # raises if Track A's scorer is not importable
    profile, _ = cs.scoring_profile_from_yaml(
        cs.CONFIG_DIR / "scoring_profiles" / f"{profile_name}.yaml"
    )
    core, site, _ = layers_for(profile)
    path = tmp_path / "criteria.yaml"
    path.write_text("mode: discovery\ntop_n: 10\n")
    outcome = parse.parse_from_file(
        path, core=core, site=site, profile=profile, cli_profile=profile.name
    )
    inputs = pipeline.RunInputs(
        request_text=request_text,
        parse=outcome,
        core=core,
        site=site,
        profile=profile,
        hazard_policy=cs.load_yaml(cs.default_paths()["hazard_policy"]),
    )
    bundle = pipeline.run(inputs, fetch=transport, sources=sources, scorer=default_scorer())
    assert bundle.run.partial is False and bundle.run.partial_reasons == []
    discovery = next(d for d in bundle.decision_log if d.step == "discovery")
    assert discovery.detail["total"] == total
    top = bundle.ranked()[:10]
    assert len(top) == 10
    for c in top:
        assert c.group.hazard is not None and c.group.literature is not None, c.composition
        assert "enrichment_missing" not in [f.value for f in c.flags], c.composition
    if profile_name == "oxide_dielectric_thin_film":
        # review F17: molecules excluded in discovery are counted in the PI view, not named
        from materials_triage.render import markdown

        excluded = {c.composition for c in bundle.excluded()}
        assert {"H2O", "CO2"} <= excluded
        pi = markdown.render_pi_summary(
            bundle, cs.site_profile_from_yaml(cs.default_paths()["site_profile"])
        )
        section = pi[pi.index("## Excluded") :].split("\n## ")[0]
        assert "structure.molecular:" in section
        assert "H2O" not in section and "CO2" not in section
    rounds = [d for d in bundle.decision_log if d.step == "enrich"]
    assert 1 <= len(rounds) <= pipeline.MAX_ENRICHMENT_ROUNDS
    assert {a.composition for a in bundle.anchors} <= set(profile.anchors)


def layers_for(
    profile: cs.ScoringProfile,
) -> tuple[cs.CoreConfig, cs.SiteProfile, cs.ScoringProfile]:
    paths = cs.default_paths()
    return cs.CoreConfig(), cs.site_profile_from_yaml(paths["site_profile"]), profile


def test_rows_the_cross_checks_exclude_are_never_classified(
    layers: Layers,
    tmp_path: Path,
    transport: DiscoveryCassettes,
    sources: pipeline.Sources,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live A1 on Haiku spent 20 of 50 classify calls on CO2, H2O, SO3 and Li2O, rows in the top
    10 before their cross-checks that the checks then excluded or pushed down. Each round now
    rescores after enrichment and classifies only what is still in the top K. Here the test
    scorer excludes BeO once its cross-checks arrive, as the hazard rule does."""
    from materials_triage.agent import classifier
    from materials_triage.records.bundle import Exclusion, ExclusionRule

    def hazard_aware(request: ScoreRequest) -> ScoredSet:
        out = gap_scorer(request)
        beo = request.groups.get("BeO")
        if beo is None or beo.literature is None:  # not cross-checked yet
            return out
        kept = [c for c in out.candidates if c.composition != "BeO"]
        for i, c in enumerate(kept, start=1):
            c.rank = i
        dropped = next(c for c in out.candidates if c.composition == "BeO")
        dropped.rank = None
        dropped.excluded = Exclusion(
            rule=ExclusionRule.HAZARD_EXCLUDE, detail="test: Be", source_ref=None
        )
        return ScoredSet(candidates=[*kept, dropped], anchors=out.anchors, note=out.note)

    seen: list[str] = []
    real = classifier.classify_hits

    def spy(**kw):  # type: ignore[no-untyped-def]
        seen.extend(comp for comp, _ in kw["hits"])
        return real(**kw)

    monkeypatch.setattr(classifier, "classify_hits", spy)
    inputs = _inputs(layers, tmp_path, band_gap_min_ev=2.0, band_gap_max_ev=3.0, top_n=3)
    bundle = pipeline.run(inputs, fetch=transport, sources=sources, scorer=hazard_aware)
    beo = next(c for c in bundle.candidates if c.composition == "BeO")
    assert beo.excluded is not None and beo.group.literature is not None  # it was cross-checked
    assert "BeO" not in seen  # and no classify request was spent on it


def test_product_sources_load_the_full_gap_compendium(sources: pipeline.Sources) -> None:
    # review F04: every composition gets the experimental gap the pinned table holds, not only
    # the hand-picked baseline oxides
    assert sources.gap_aggregates["MgO"].n == 4
    assert "Lu2O3" in sources.gap_aggregates and "P2O5" not in sources.gap_aggregates
    assert sources.versions["expt_gap"].startswith("2d0980e3")
