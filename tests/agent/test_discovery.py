"""Discovery mode over the recorded 2 to 3 eV oxide cassette: paged in full, scored on
summary data, the top K enriched, and refused above the ceiling. The scorer here is a
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


def test_discovery_filter_keeps_the_cutoff_out_of_the_api_query(layers: Layers) -> None:
    profile = layers[2]
    f = pipeline.discovery_filter(
        cs.QuerySettings(
            profile=profile.name, mode="discovery", band_gap_min_ev=2.0, band_gap_max_ev=3.0
        ),
        profile,
    )
    assert f.params() == {
        "elements": "O",
        "nelements_min": "2",
        "nelements_max": "3",
        "band_gap_min": "2.0",
        "band_gap_max": "3.0",
    }


def test_discovery_pages_everything_scores_summaries_and_enriches_the_top_k(
    layers: Layers, tmp_path: Path, transport: DiscoveryCassettes, sources: pipeline.Sources
) -> None:
    inputs = _inputs(layers, tmp_path, band_gap_min_ev=2.0, band_gap_max_ev=3.0, top_n=3)
    bundle = pipeline.run(inputs, fetch=transport, sources=sources, scorer=gap_scorer)
    steps = [d.step for d in bundle.decision_log]
    assert steps[:5] == ["start", "discovery", "enrich", "classify", "score"]
    discovery = next(d for d in bundle.decision_log if d.step == "discovery")
    assert discovery.detail["total"] == 3016 and "3016 summary documents" in discovery.summary
    assert len(bundle.candidates) > 1000 and bundle.criteria.mode == "discovery"
    ranked = bundle.ranked()
    gaps = [c.score.total for c in ranked if c.score]
    assert gaps == sorted(gaps, reverse=True) and gaps[0] is not None and gaps[0] <= 3.0
    enrich = next(d for d in bundle.decision_log if d.step == "enrich")
    assert "of 4 top candidates" in enrich.summary  # top 3 plus the SiO2 anchor
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
