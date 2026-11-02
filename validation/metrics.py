"""Validation metrics over a ProvenanceBundle. Pure functions; every output names the rows
it was computed from so the report can show them.

- Yim 2015: Spearman of scorer rank against the paper's figure-of-merit order, per table,
  over the compositions the scorer ranked. Excluded compositions are listed with their rule,
  never silently dropped. Negatives must be excluded or flagged. Compositions with no usable
  abstract stay in the correlation and are listed separately under evidence tier "no abstract".
- Recall at K for the owner's known dielectrics.
- Negative controls: each named control is excluded or flagged with its rule shown.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from materials_triage.adapters.common import reduced_formula
from materials_triage.records.bundle import Candidate, Flag, ProvenanceBundle
from validation.groups import literature_state
from validation.spearman import spearman
from validation.yim import YimGroundTruth

ROOT = Path(__file__).resolve().parents[1]
KNOWN_DIELECTRICS = ROOT / "fixtures" / "validation" / "known_dielectrics.yaml"

HAZARD_FLAGS = {Flag.HAZARD_FLAG, Flag.HAZARD_UNKNOWN, Flag.PROCESS_HAZARD}


def _by_composition(bundle: ProvenanceBundle) -> dict[str, Candidate]:
    return {c.composition: c for c in bundle.candidates}


# ----------------------------------------------------------------------------- Yim 2015


@dataclass(frozen=True)
class YimPair:
    composition: str
    yim_best_fom: float
    yim_rank: float  # average rank within the table, best FOM = 1
    scorer_rank: int


@dataclass(frozen=True)
class YimTable:
    table: int
    n_in_table: int
    n_ranked: int
    rho: float | None
    reason: str | None
    pairs: list[YimPair]
    excluded: list[dict[str, str]]  # composition, rule, detail
    absent: list[str]  # in the table, not in the bundle at all


@dataclass(frozen=True)
class NegativeOutcome:
    composition: str
    status: str  # excluded | flagged | ranked_unflagged | absent
    rule: str | None
    flags: list[str]
    rank: int | None


@dataclass(frozen=True)
class NoAbstractRow:
    composition: str
    state: str  # no_match | no_abstract
    rank: int | None
    excluded_rule: str | None


@dataclass(frozen=True)
class YimReport:
    citation: str
    doi: str
    fixture_sha256: str
    polymorph_rule: str
    tables: list[YimTable]
    negatives: list[NegativeOutcome]
    no_abstract: list[NoAbstractRow]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _average_ranks_desc(values: list[float]) -> list[float]:
    """Rank 1 for the largest value, ties averaged."""
    from validation.spearman import average_ranks

    return average_ranks([-v for v in values])


def yim_table(bundle: ProvenanceBundle, gt: YimGroundTruth, table: int) -> YimTable:
    order = gt.table_order(table)
    cands = _by_composition(bundle)
    yim_ranks = _average_ranks_desc([f for _, f in order])
    pairs: list[YimPair] = []
    excluded: list[dict[str, str]] = []
    absent: list[str] = []
    for (comp, fom), yrank in zip(order, yim_ranks, strict=True):
        c = cands.get(comp)
        if c is None:
            absent.append(comp)
        elif c.rank is not None:
            pairs.append(YimPair(comp, fom, yrank, c.rank))
        elif c.excluded is not None:
            excluded.append(
                {"composition": comp, "rule": str(c.excluded.rule), "detail": c.excluded.detail}
            )
        else:
            excluded.append({"composition": comp, "rule": "unranked", "detail": "no rank, no rule"})
    res = spearman([p.yim_rank for p in pairs], [float(p.scorer_rank) for p in pairs])
    return YimTable(
        table=table,
        n_in_table=len(order),
        n_ranked=len(pairs),
        rho=res.rho,
        reason=res.reason,
        pairs=pairs,
        excluded=excluded,
        absent=absent,
    )


def negative_outcome(bundle: ProvenanceBundle, composition: str) -> NegativeOutcome:
    c = _by_composition(bundle).get(composition)
    if c is None:
        return NegativeOutcome(composition, "absent", None, [], None)
    flags = [str(f) for f in c.flags]
    if c.excluded is not None:
        return NegativeOutcome(composition, "excluded", str(c.excluded.rule), flags, None)
    if any(f in HAZARD_FLAGS for f in c.flags):
        return NegativeOutcome(composition, "flagged", None, flags, c.rank)
    return NegativeOutcome(composition, "ranked_unflagged", None, flags, c.rank)


def no_abstract_rows(bundle: ProvenanceBundle, compositions: list[str]) -> list[NoAbstractRow]:
    cands = _by_composition(bundle)
    rows = []
    for comp in sorted(compositions):
        c = cands.get(comp)
        if c is None:
            continue
        state = literature_state(c.group.literature)
        if state == "has_abstracts":
            continue
        rows.append(
            NoAbstractRow(comp, state, c.rank, None if c.excluded is None else str(c.excluded.rule))
        )
    return rows


def yim_report(bundle: ProvenanceBundle, gt: YimGroundTruth) -> YimReport:
    return YimReport(
        citation=gt.citation,
        doi=gt.doi,
        fixture_sha256=gt.fixture_sha256,
        polymorph_rule=(
            "one entry per composition per table, ordered by its best f_fom in that table; "
            "ties share average ranks (owner decision 2026-11-02)"
        ),
        tables=[yim_table(bundle, gt, t) for t in gt.tables()],
        negatives=[negative_outcome(bundle, n) for n in gt.negatives],
        no_abstract=no_abstract_rows(bundle, gt.compositions()),
    )


# ----------------------------------------------------------------------------- recall at K


@dataclass(frozen=True)
class RecallReport:
    k: int
    known: list[str]
    source: str
    hits: list[dict[str, Any]]  # composition, rank
    misses: list[dict[str, Any]]  # composition, rank or excluded rule or absent
    recall: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_known_dielectrics(path: Path = KNOWN_DIELECTRICS) -> tuple[list[str], int, str]:
    data = yaml.safe_load(path.read_text())
    if data.get("status") != "entered":
        raise ValueError(f"{path} is not entered")
    comps = [reduced_formula(c) for c in data["compositions"]]
    return comps, int(data["k"]), str(data["source"]["citation"])


def recall_at_k(bundle: ProvenanceBundle, known: list[str], k: int, source: str) -> RecallReport:
    cands = _by_composition(bundle)
    hits: list[dict[str, Any]] = []
    misses: list[dict[str, Any]] = []
    for comp in known:
        c = cands.get(comp)
        if c is None:
            misses.append({"composition": comp, "why": "absent from the bundle"})
        elif c.rank is not None and c.rank <= k:
            hits.append({"composition": comp, "rank": c.rank})
        elif c.rank is not None:
            misses.append({"composition": comp, "rank": c.rank, "why": f"ranked below {k}"})
        else:
            rule = None if c.excluded is None else str(c.excluded.rule)
            misses.append({"composition": comp, "why": f"excluded: {rule}"})
    recall = None if not known else len(hits) / len(known)
    return RecallReport(
        k=k, known=list(known), source=source, hits=hits, misses=misses, recall=recall
    )


# ----------------------------------------------------------------------------- negative controls


@dataclass(frozen=True)
class NegativeControls:
    named: list[NegativeOutcome]  # owner's list
    theoretical_only: list[NegativeOutcome]  # groups with no observed polymorph
    all_handled: bool = field(default=False)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def negative_controls(bundle: ProvenanceBundle, named: list[str]) -> NegativeControls:
    named_out = [negative_outcome(bundle, reduced_formula(n)) for n in named]
    theoretical = [
        negative_outcome(bundle, c.composition)
        for c in bundle.candidates
        if c.group.polymorphs.lowest_observed is None and c.group.polymorphs.total > 0
    ]
    # A theoretical-only group is handled when it is excluded or carries the theoretical flag.
    theo_ok = all(
        o.status == "excluded" or str(Flag.GROUND_STATE_IS_THEORETICAL) in o.flags
        for o in theoretical
    )
    named_ok = all(o.status in ("excluded", "flagged") for o in named_out)
    return NegativeControls(
        named=named_out, theoretical_only=theoretical, all_handled=theo_ok and named_ok
    )
