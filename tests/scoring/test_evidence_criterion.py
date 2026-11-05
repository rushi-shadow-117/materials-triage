"""Evidence read and found wanting scores 0.0; evidence never read stays missing (owner decision
on PR #18, Nov 5)."""

from __future__ import annotations

from datetime import UTC, datetime

from materials_triage.records import Provenance
from materials_triage.records.bundle import EvidenceHit, EvidenceLabel
from materials_triage.scoring import criteria as crit

TIERS = {
    "dielectric_characterized": 1.0,
    "thin_film_deposited": 0.75,
    "bulk_synthesized": 0.5,
    "computed_only": 0.25,
}
PROV = Provenance(
    source="openalex",
    source_record_id="W1",
    raw_response_id=None,
    raw_sha256="0" * 64,
    fetched_at=datetime(2026, 11, 5, tzinfo=UTC),
)


def _hit(
    n: int, label: EvidenceLabel, *, read: bool = True, note: str | None = None
) -> EvidenceHit:
    return EvidenceHit(
        composition="P2O5",
        openalex_id=f"https://openalex.org/W{n}",
        label=label,
        deposition_method=None,
        supporting_sentence="A sentence." if label in crit.READ_LABELS else None,
        verified=label not in (EvidenceLabel.NOT_RELEVANT, EvidenceLabel.UNCLASSIFIED),
        verifier_note=note,
        classifier_cache_key=f"k{n}" if read else None,
        provenance=PROV,
    )


def _score(hits: list[EvidenceHit]) -> crit.CriterionResult:
    return crit.evidence(hits, tiers=TIERS, tier_min=None, literature=None, source_ref="p")


def test_abstracts_read_with_no_usable_label_score_zero() -> None:
    # the live A1's P2O5: every label named another material
    hits = [
        _hit(i, EvidenceLabel.NOT_RELEVANT, note="evidence names another material")
        for i in range(4)
    ] + [_hit(9, EvidenceLabel.NOT_RELEVANT)]
    r = _score(hits)
    assert r.normalized == 0.0 and r.raw_value == 0.0
    assert r.missing_reason is None
    assert r.source == "no supporting evidence found in 5 abstracts"


def test_unread_abstracts_stay_missing() -> None:
    unread = [_hit(i, EvidenceLabel.UNCLASSIFIED, read=False) for i in range(3)]
    r = _score(unread)
    assert r.normalized is None and r.missing_reason == "unclassified"
    # one read and found wanting, the rest cut off by the budget: still not read in full
    mixed = [_hit(0, EvidenceLabel.NOT_RELEVANT), *unread]
    assert _score(mixed).normalized is None
    assert _score([]).normalized is None and _score(None).normalized is None
    no_abstract = [_hit(0, EvidenceLabel.NO_ABSTRACT, read=False)]
    assert _score(no_abstract).normalized is None


def test_a_usable_label_still_scores_its_tier() -> None:
    hits = [_hit(0, EvidenceLabel.NOT_RELEVANT), _hit(1, EvidenceLabel.THIN_FILM_DEPOSITED)]
    assert _score(hits).normalized == 0.75
