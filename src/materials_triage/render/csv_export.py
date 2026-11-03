"""CSV export: one row per candidate and anchor, every number through `precision`."""

from __future__ import annotations

import csv
import io

from materials_triage.config.schema import CRITERIA
from materials_triage.records.bundle import Anchor, Candidate, ProvenanceBundle
from materials_triage.render import precision

FIXED = [
    "run_id",
    "composition",
    "kind",
    "rank",
    "would_rank",
    "out_of",
    "total",
    "excluded_rule",
    "band_gap_source",
    "flags",
    "caveats",
    "ground_state_mp_id",
    "polymorph_count",
]


def header() -> list[str]:
    cols = list(FIXED)
    for c in CRITERIA:
        cols += [f"{c}_raw", f"{c}_unit", f"{c}_source", f"{c}_record_id"]
    return cols


def _row(bundle: ProvenanceBundle, row: Candidate | Anchor, units: str) -> list[str]:
    scores = {cs.criterion: cs for cs in row.score.criteria} if row.score else {}
    excluded = row.excluded
    p = row.group.polymorphs
    out = [
        str(bundle.run.run_id),
        row.composition,
        "anchor" if isinstance(row, Anchor) else "candidate",
        "" if isinstance(row, Anchor) or row.rank is None else precision.quantize(row.rank, 0),
        ""
        if not isinstance(row, Anchor) or row.would_rank is None
        else precision.quantize(row.would_rank, 0),
        precision.quantize(row.out_of, 0) if isinstance(row, Anchor) else "",
        ""
        if row.score is None or row.score.total is None
        else precision.fmt(row.score.total, "score"),
        excluded.rule.value if excluded else "",
        (row.score.band_gap_source or "") if row.score else "",
        ";".join(f.value for f in row.flags),
        ";".join(c.id.value + (f"[{c.subject}]" if c.subject else "") for c in row.caveats),
        (p.ground_state.mp_id or "") if p.ground_state else "",
        precision.quantize(p.total, 0),
    ]
    for c in CRITERIA:
        cs = scores.get(c)
        if cs is None or cs.raw_value is None:
            out += ["", cs.raw_unit or "" if cs else "", cs.source or "" if cs else "", ""]
            continue
        out += [
            precision.fmt_number(cs.raw_value, cs.raw_unit, units),
            precision.display_unit(cs.raw_unit, units)[1] or "",
            cs.source or "",
            cs.provenance.source_record_id if cs.provenance else "",
        ]
    return out


def export_csv(bundle: ProvenanceBundle, *, units: str = "eV") -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header())
    for row in [*bundle.ranked(), *bundle.excluded()]:
        writer.writerow(_row(bundle, row, units))
    for anchor in bundle.anchors:
        writer.writerow(_row(bundle, anchor, units))
    return buf.getvalue()
