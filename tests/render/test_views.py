"""The selection chart in the view model (Track H item 5): every point's numbers are the
bundle's own, k comes from the scored polymorph's DFPT record, a row without k is listed as
unplotted, and the PI view carries no record ids."""

from __future__ import annotations

import json
from pathlib import Path

from materials_triage.records.bundle import ProvenanceBundle
from materials_triage.render.caveats import CaveatConfig
from materials_triage.render.views import _ticks, build

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"


def _bundle() -> ProvenanceBundle:
    return ProvenanceBundle.model_validate(json.loads(SAMPLE.read_text()))


def test_chart_points_are_the_bundles_values_with_their_records() -> None:
    bundle = _bundle()
    view = build(bundle, CaveatConfig.load(), units="eV", hide_ids=False)
    assert view.chart is not None
    by_name = {p.composition: p for p in view.chart.points}
    hfo2 = next(c for c in bundle.candidates if c.composition == "HfO2")
    assert hfo2.score is not None
    gap = next(cs for cs in hfo2.score.criteria if cs.criterion == "band_gap")
    scored = hfo2.group.polymorphs.scored
    assert scored is not None
    e_total = scored.dielectric["e_total"]
    p = by_name["HfO2"]
    assert p.gap == gap.raw_value and p.k == e_total.value
    assert p.gap_text == "5.55 eV" and p.k_text == "18.7"
    assert p.k_source.startswith("materials_project")
    assert e_total.provenance.source_record_id in p.record_ids
    assert p.status == "shortlist"
    assert by_name["SiO2"].status == "anchor"
    # rows whose scored polymorph has no computed k are listed, never plotted
    assert "ThO2" not in by_name
    # ThO2 is excluded, not shown: counted, not named (Track H sweep)
    assert not any(u.startswith("ThO2") for u in view.chart.unplotted)
    assert view.chart.others_not_plotted >= 1
    assert view.chart.x_label == "band gap (eV)"
    assert [t.text for t in view.chart.x_ticks][:3] == ["0.00 eV", "5.00 eV", "10.00 eV"]


def test_pi_view_chart_has_no_record_ids_and_mev_units_apply() -> None:
    bundle = _bundle()
    view = build(bundle, CaveatConfig.load(), units="meV", hide_ids=True)
    assert view.chart is not None and view.chart.points
    assert all(p.record_ids == [] for p in view.chart.points)
    hfo2 = next(p for p in view.chart.points if p.composition == "HfO2")
    assert hfo2.gap_text == "5550 meV" and hfo2.gap == 5550.0
    assert view.chart.x_label == "band gap (meV)"


def test_ticks_are_round_and_start_at_zero() -> None:
    assert [t.value for t in _ticks([7.6, 3.2], "eV", "eV")] == [0.0, 2.0, 4.0, 6.0, 8.0]
    assert [t.text for t in _ticks([63.2], "1", "eV")] == ["0.0", "20.0", "40.0", "60.0", "80.0"]
    assert _ticks([], "eV", "eV") == []


def _unenrich(bundle: ProvenanceBundle, names: set[str]) -> ProvenanceBundle:
    from materials_triage.records.bundle import Flag

    rows = []
    for c in bundle.candidates:
        if c.composition in names:
            c = c.model_copy(update={"flags": [*c.flags, Flag.ENRICHMENT_MISSING]})
        rows.append(c)
    return bundle.model_copy(update={"candidates": rows})


def test_chart_and_counts_leave_out_rows_scored_on_summary_data_only() -> None:
    """Track H sweep: the chart listed about 1,600 unplotted rows and compared against rows
    never cross-checked."""
    bundle = _bundle()
    ranked = [c.composition for c in bundle.ranked()]
    tail = set(ranked[2:])
    view = build(_unenrich(bundle, tail), CaveatConfig.load(), units="eV", hide_ids=True)
    assert view.chart is not None
    allowed = set(ranked[:2]) | {"SiO2"} | {c.composition for c in bundle.excluded()}
    plotted = {p.composition for p in view.chart.points}
    assert plotted <= allowed and not (plotted & tail)  # no summary-only row is plotted
    named = {u.split(":")[0] for u in view.chart.unplotted}
    shown = {r.composition for r in view.rows}
    assert named <= shown | {a.composition for a in bundle.anchors}
    assert view.chart.others_not_plotted >= 1


def test_excluded_rows_are_counted_by_rule_and_ordered_cross_checked_first() -> None:
    from materials_triage.records.bundle import Exclusion, ExclusionRule

    bundle = _bundle()
    rows = []
    for i, c in enumerate(bundle.candidates[:4]):
        rule = ExclusionRule.HAZARD_EXCLUDE if i % 2 else ExclusionRule.STABILITY_CUTOFF
        rows.append(
            c.model_copy(update={"rank": None, "excluded": Exclusion(rule=rule, detail="t")})
        )
    rows += bundle.candidates[4:]
    b = _unenrich(bundle.model_copy(update={"candidates": rows}), {rows[0].composition})
    view = build(b, CaveatConfig.load(), units="eV")
    counts = {e.rule: e.count for e in view.excluded_by_rule}
    before = sum(
        1 for c in bundle.excluded() if c.excluded and c.excluded.rule.value == "hazard.exclude"
    )
    assert sum(counts.values()) == len(b.excluded())
    assert counts["hazard.exclude"] == before + 2
    assert view.excluded[-1].composition == rows[0].composition  # unchecked goes last
