"""Yim Spearman, negatives, no-abstract tier, recall at K, and negative controls on synthetic
bundles with known ranks, plus the real Yim ground truth."""

import pytest
from validation.metrics import (
    load_known_dielectrics,
    negative_controls,
    negative_outcome,
    recall_at_k,
    yim_report,
    yim_table,
)
from validation.yim import load_yim

from materials_triage.records.bundle import ExclusionRule, Flag
from tests.evals.bundles import bundle, candidate, ranked_bundle

GT = load_yim()


def test_perfect_agreement_with_table_one_gives_rho_one() -> None:
    order = [c for c, _ in GT.table_order(1)]
    rep = yim_table(ranked_bundle(order), GT, 1)
    # Table 1 has a tie (AlLiO2 and Ba3(PO4)2 at f_fom 85), so even a perfect ordering is
    # slightly below 1 under average ranks; the exact value is the Spearman of the pairs.
    assert rep.rho is not None and rep.rho > 0.99
    assert rep.n_ranked == rep.n_in_table == 11 and rep.excluded == []


def test_reversed_order_gives_minus_one_and_ties_are_averaged() -> None:
    order = [c for c, _ in GT.table_order(3)]
    rep = yim_table(ranked_bundle(list(reversed(order))), GT, 3)
    assert rep.rho is not None and rep.rho < -0.99
    # Table 3 has tied f_fom values (several at 85 and 89), so some Yim ranks are fractional.
    assert any(p.yim_rank != int(p.yim_rank) for p in rep.pairs)


def test_excluded_compositions_are_listed_with_their_rule_not_dropped() -> None:
    order = [c for c, _ in GT.table_order(1)]
    cands = [candidate(c, i + 1) for i, c in enumerate(order) if c != "BeO"]
    cands.append(candidate("BeO", excluded=ExclusionRule.HAZARD_EXCLUDE))
    rep = yim_table(bundle(cands), GT, 1)
    assert rep.n_ranked == 10 and rep.excluded == [
        {"composition": "BeO", "rule": "hazard.exclude", "detail": "BeO hazard.exclude"}
    ]
    assert rep.absent == []


def test_absent_compositions_are_reported_and_too_few_pairs_gives_a_reason() -> None:
    rep = yim_table(ranked_bundle(["YBO3"]), GT, 1)
    assert rep.n_ranked == 1 and rep.rho is None and rep.reason == "fewer than two pairs"
    assert len(rep.absent) == 10


def test_negative_outcomes_cover_every_state() -> None:
    b = bundle(
        [
            candidate("BeO", excluded=ExclusionRule.HAZARD_EXCLUDE),
            candidate("TiCdO3", 3, flags=[Flag.HAZARD_FLAG]),
            candidate("HfPbO3", 4),
        ]
    )
    assert negative_outcome(b, "BeO").status == "excluded"
    assert negative_outcome(b, "BeO").rule == "hazard.exclude"
    assert negative_outcome(b, "TiCdO3").status == "flagged"
    assert negative_outcome(b, "HfPbO3").status == "ranked_unflagged"
    assert negative_outcome(b, "ZrPbO3").status == "absent"
    controls = negative_controls(b, ["BeO", "CdTiO3", "PbHfO3"])
    assert controls.all_handled is False
    assert [o.status for o in controls.named] == ["excluded", "flagged", "ranked_unflagged"]


def test_theoretical_only_groups_must_be_flagged_or_excluded() -> None:
    ok = bundle([candidate("X2O3", 1, observed=False, flags=[Flag.GROUND_STATE_IS_THEORETICAL])])
    bad = bundle([candidate("X2O3", 1, observed=False)])
    assert negative_controls(ok, []).all_handled is True
    assert negative_controls(bad, []).all_handled is False
    assert negative_controls(bad, []).theoretical_only[0].composition == "X2O3"


def test_no_abstract_rows_stay_ranked_and_are_listed_separately() -> None:
    b = bundle(
        [
            candidate("HfO2", 1, hits=3),
            candidate("Li4CO4", 2, hits=0, matched_total=0),
            candidate("NaIO3", 3, hits=0, matched_total=3),
            candidate("CaB4O7", excluded=ExclusionRule.STABILITY_CUTOFF, hits=0, matched_total=0),
        ]
    )
    rep = yim_report(b, GT)
    rows = {r.composition: r for r in rep.no_abstract}
    assert set(rows) == {"Li4CO4", "NaIO3", "CaB4O7"}
    assert rows["Li4CO4"].state == "no_match" and rows["Li4CO4"].rank == 2
    assert rows["NaIO3"].state == "no_abstract" and rows["NaIO3"].rank == 3
    assert rows["CaB4O7"].excluded_rule == "stability.cutoff"
    assert rep.polymorph_rule.startswith("one entry per composition per table")
    assert rep.doi == GT.doi


def test_recall_at_k_counts_hits_and_explains_each_miss() -> None:
    known, k, source = load_known_dielectrics()
    assert known == ["HfO2", "ZrO2", "Al2O3", "Y2O3", "Ta2O5"] and k == 5
    b = bundle(
        [
            candidate("Al2O3", 1),
            candidate("HfO2", 2),
            candidate("La2O3", 3),
            candidate("Y2O3", 4),
            candidate("ZrO2", 5),
            candidate("Ta2O5", 6),
        ]
    )
    rep = recall_at_k(b, known, k, source)
    assert rep.recall == pytest.approx(0.8)
    assert [h["composition"] for h in rep.hits] == ["HfO2", "ZrO2", "Al2O3", "Y2O3"]
    assert rep.misses == [{"composition": "Ta2O5", "rank": 6, "why": "ranked below 5"}]
    rep2 = recall_at_k(
        bundle([candidate("HfO2", excluded=ExclusionRule.STABILITY_CUTOFF)]), known, k, source
    )
    assert rep2.recall == 0.0 and rep2.misses[0]["why"] == "excluded: stability.cutoff"
    assert rep2.misses[1]["why"] == "absent from the bundle"
