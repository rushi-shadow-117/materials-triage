"""Band gap calibration on the recorded oxides: TBmBJ and PBE against the experimental median.

Pairs are formed where a composition has an experimental median (expt_gap compendium) and a
computed gap on its scored polymorph. The mean absolute error is reported with n and every
pair, so a reader can recompute it. The conflict tolerance is defined by the scoring profile
as twice the TBmBJ MAE; this module derives the number and the data hash that pins it. It
does not write config.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from materials_triage.scoring.polymorphs import select_scored
from validation.groups import LoadedGroup, Snapshots

TBMBJ_KEY = "jarvis_tbmbj"
PBE_KEY = "mp_summary"


@dataclass(frozen=True)
class GapPair:
    composition: str
    experimental_median: float
    experimental_n: int
    computed: float
    method: str
    mp_id: str | None
    abs_error: float


@dataclass(frozen=True)
class MethodError:
    method: str
    n: int
    mae: float | None
    pairs: list[GapPair]
    without_pair: list[str]  # compositions with an experimental median but no computed value


@dataclass(frozen=True)
class CalibrationReport:
    tbmbj: MethodError
    pbe: MethodError
    conflict_tolerance_ev: float | None
    derivation: str
    data_sha256: str
    snapshot_shas: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _method_error(groups: dict[str, LoadedGroup], key: str, label: str) -> MethodError:
    pairs: list[GapPair] = []
    without: list[str] = []
    for comp, lg in sorted(groups.items()):
        agg = lg.group.experimental_gaps
        if agg is None:
            continue
        scored = select_scored(lg.group)
        v = None if scored is None else scored.band_gap.get(key)
        if v is None or v.value is None:
            without.append(comp)
            continue
        pairs.append(
            GapPair(
                composition=comp,
                experimental_median=agg.median,
                experimental_n=agg.n,
                computed=v.value,
                method=label,
                mp_id=scored.ids.mp if scored else None,
                abs_error=abs(v.value - agg.median),
            )
        )
    mae = None if not pairs else sum(p.abs_error for p in pairs) / len(pairs)
    return MethodError(method=label, n=len(pairs), mae=mae, pairs=pairs, without_pair=without)


def calibrate(groups: dict[str, LoadedGroup], snapshots: Snapshots) -> CalibrationReport:
    tbmbj = _method_error(groups, TBMBJ_KEY, "tbmbj")
    pbe = _method_error(groups, PBE_KEY, "pbe")
    tolerance = None if tbmbj.mae is None else round(2 * tbmbj.mae, 3)
    payload = {
        "tbmbj": [asdict(p) for p in tbmbj.pairs],
        "pbe": [asdict(p) for p in pbe.pairs],
        "snapshots": snapshots.shas(),
    }
    sha = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return CalibrationReport(
        tbmbj=tbmbj,
        pbe=pbe,
        conflict_tolerance_ev=tolerance,
        derivation=(
            f"conflict_tolerance_ev = 2 x MAE(TBmBJ vs experimental median) over n={tbmbj.n} "
            "recorded oxides with both values; pairs listed; rounded to 3 decimals"
        ),
        data_sha256=sha,
        snapshot_shas=snapshots.shas(),
    )
