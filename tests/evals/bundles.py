"""Synthetic bundles with known ranks for metric tests. Shapes follow bundle version 2."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from materials_triage.records import LiteratureSearchResult, Provenance
from materials_triage.records.bundle import (
    Anchor,
    Candidate,
    CompositionSummary,
    ConfirmedCriteria,
    Exclusion,
    ExclusionRule,
    FetchMode,
    Flag,
    PolymorphSummary,
    PolymorphSummaryRow,
    ProvenanceBundle,
    RunMetadata,
)

NOW = datetime(2026, 11, 2, tzinfo=UTC)


def prov(rid: str) -> Provenance:
    return Provenance(
        source="materials_project",
        source_record_id=rid,
        raw_response_id=None,
        raw_sha256="0" * 64,
        fetched_at=NOW,
    )


def row(mp_id: str, observed: bool | None = True) -> PolymorphSummaryRow:
    return PolymorphSummaryRow(
        mp_id=mp_id,
        spacegroup_number=None,
        spacegroup_symbol=None,
        hull_energy=None,
        observed=observed,
        theoretical=None if observed is None else not observed,
    )


def summary(
    composition: str, *, hits: int = 1, matched_total: int | None = None, observed: bool = True
) -> CompositionSummary:
    ground = row("mp-1", observed=observed)
    lit = LiteratureSearchResult(
        composition=composition,
        query=f"{composition} thin film",
        scope="title_and_abstract",
        matched_total=hits if matched_total is None else matched_total,
        matched_with_abstract=hits,
        hits=[],
    )
    # hits are represented by the count only; the metric reads `hits` emptiness
    if hits:
        from materials_triage.records import LiteratureHit

        lit.hits = [
            LiteratureHit(
                openalex_id=f"W{i}",
                doi=None,
                title=None,
                year=None,
                abstract_text="x",
                abstract_index_sha256=None,
                is_oa=None,
                license=None,
                source_name=None,
                landing_page_url=None,
                query=lit.query,
                scope=lit.scope,
                quote_verifiable=True,
                cost_usd=None,
                provenance=prov(f"W{i}"),
            )
            for i in range(hits)
        ]
    return CompositionSummary(
        composition=composition,
        polymorphs=PolymorphSummary(
            composition_id=composition,
            total=1,
            observed_count=1 if observed else 0,
            theoretical_count=0 if observed else 1,
            unknown_count=0,
            ground_state=ground,
            ground_state_is_theoretical=not observed,
            lowest_observed=ground if observed else None,
            scored=ground,
            top_by_hull=[ground],
        ),
        experimental_gaps=None,
        hazard=None,
        literature=lit,
    )


def candidate(
    composition: str,
    rank: int | None = None,
    *,
    excluded: ExclusionRule | None = None,
    flags: list[Flag] | None = None,
    hits: int = 1,
    matched_total: int | None = None,
    observed: bool = True,
) -> Candidate:
    return Candidate(
        composition=composition,
        group=summary(composition, hits=hits, matched_total=matched_total, observed=observed),
        score=None,
        rank=rank,
        excluded=None
        if excluded is None
        else Exclusion(rule=excluded, detail=f"{composition} {excluded}", source_ref="test"),
        flags=flags or [],
    )


def bundle(candidates: list[Candidate], anchors: list[Anchor] | None = None) -> ProvenanceBundle:
    return ProvenanceBundle(
        run=RunMetadata(
            run_id=UUID("00000000-0000-4000-8000-0000000000aa"),
            started_at=NOW,
            finished_at=NOW,
            config_sha="c" * 64,
            profile_name="test",
            profile_version="0",
            policy_version="0",
            prompt_hash=None,
            model_version=None,
            provider=None,
            source_versions={},
            fetch_mode=FetchMode.REPLAY,
            partial=False,
        ),
        criteria=ConfirmedCriteria(
            request_text="test",
            parsed_by="criteria_file",
            confirmed_at=NOW,
            mode="candidate_list",
            candidate_list=[c.composition for c in candidates],
            effective_settings={},
        ),
        candidates=candidates,
        anchors=anchors or [],
    )


def ranked_bundle(order: list[str], **kw: object) -> ProvenanceBundle:
    return bundle([candidate(c, i + 1) for i, c in enumerate(order)])
