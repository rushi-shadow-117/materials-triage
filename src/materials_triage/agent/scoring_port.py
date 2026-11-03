"""The scorer behind a port.

The pipeline hands the scorer every fetched CompositionGroup and the effective config and
gets back scored candidates and anchors. Track A's `scoring.scorer` is adapted here when it
is present; until then `SampleBundleScorer` copies scores, ranks, exclusions, flags, caveats,
and sensitivity from the sample bundle by composition, and the run note says so.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from materials_triage.config.schema import EffectiveConfig, ScoringProfile
from materials_triage.records import CompositionGroup, ReferenceValue
from materials_triage.records.bundle import Anchor, Candidate, ProvenanceBundle
from materials_triage.scoring.polymorphs import select_scored, summarize_group

ROOT = Path(__file__).resolve().parents[3]
SAMPLE_BUNDLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"


@dataclass
class ScoreRequest:
    groups: dict[str, CompositionGroup]  # composition -> full group, fetch order
    effective: EffectiveConfig
    profile: ScoringProfile
    hazard_policy: dict[str, Any]
    reference_values: dict[str, list[ReferenceValue]] = field(default_factory=dict)
    requested_mp: dict[str, str] = field(default_factory=dict)  # composition -> MP id the PI named


@dataclass
class ScoredSet:
    candidates: list[Candidate]
    anchors: list[Anchor]
    note: str | None = None


Scorer = Callable[[ScoreRequest], ScoredSet]


class ScorerUnavailableError(RuntimeError):
    pass


def track_a_scorer() -> Scorer:
    """Adapt Track A's scorer when it has merged. The adapter is the only place that changes
    on rebase."""
    try:
        module = importlib.import_module("materials_triage.scoring.scorer")
    except ImportError as e:
        raise ScorerUnavailableError(
            "Track A scorer (materials_triage.scoring.scorer) is not merged"
        ) from e
    score = getattr(module, "score", None)
    if score is None:
        raise ScorerUnavailableError("materials_triage.scoring.scorer has no score()")

    def adapter(request: ScoreRequest) -> ScoredSet:
        result = score(
            groups=request.groups,
            effective=request.effective,
            profile=request.profile,
            hazard_policy=request.hazard_policy,
            reference_values=request.reference_values,
            requested_mp=request.requested_mp,
        )
        return ScoredSet(candidates=list(result.candidates), anchors=list(result.anchors))

    return adapter


class SampleBundleScorer:
    """Stand-in until Track A merges: copies the sample bundle's scoring by composition.
    Compositions the sample does not hold raise, so nothing is ever invented."""

    NOTE = (
        "scores, ranks, exclusions, flags, caveats, and sensitivity copied from "
        "fixtures/bundles/sample_bundle.json (illustrative); Track A scorer not merged"
    )

    def __init__(self, sample: ProvenanceBundle | None = None) -> None:
        self.sample = sample or ProvenanceBundle.model_validate_json(SAMPLE_BUNDLE.read_text())
        self._candidates = {c.composition: c for c in self.sample.candidates}
        self._anchors = {a.composition: a for a in self.sample.anchors}

    def __call__(self, request: ScoreRequest) -> ScoredSet:
        cutoff = request.profile.stability.cutoff_mev_per_atom
        candidates: list[Candidate] = []
        anchors: list[Anchor] = []
        for comp, group in request.groups.items():
            summary = summarize_group(
                group,
                scored=select_scored(group, requested_mp=request.requested_mp.get(comp)),
                cutoff_mev=cutoff,
                reference_values=request.reference_values.get(comp),
            )
            if comp in self._anchors:
                anchors.append(self._anchors[comp].model_copy(update={"group": summary}))
            elif comp in self._candidates:
                candidates.append(self._candidates[comp].model_copy(update={"group": summary}))
            else:
                raise ScorerUnavailableError(
                    f"{comp} is not in the sample bundle; the stand-in scorer cannot score it"
                )
        ranked = sorted((c for c in candidates if c.rank is not None), key=lambda c: c.rank or 0)
        for i, c in enumerate(ranked, start=1):
            c.rank = i
        for a in anchors:
            a.out_of = len(ranked)
            if a.would_rank is not None:
                a.would_rank = min(a.would_rank, len(ranked) + 1)
        return ScoredSet(candidates=candidates, anchors=anchors, note=self.NOTE)


def default_scorer() -> Scorer:
    """Track A's scorer when merged, else the sample stand-in."""
    try:
        return track_a_scorer()
    except ScorerUnavailableError:
        return SampleBundleScorer()
