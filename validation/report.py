"""Run the validation study and write validation/results/*.json.

The scorer is a parameter: `run_validation(score=...)` takes any callable from loaded groups
to a ProvenanceBundle; `validation.track_a` provides the real one and the results file names
it in `scorer.name`. Results carry no timestamps so re-running on the same inputs is
byte-identical.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from materials_triage.records.bundle import ProvenanceBundle
from validation.calibration import calibrate
from validation.groups import (
    LoadedGroup,
    cassette_manifest_path,
    load_compositions,
    load_groups,
    load_snapshots,
)
from validation.metrics import (
    load_known_dielectrics,
    negative_controls,
    recall_at_k,
    yim_report,
    yim_table,
)
from validation.yim import YimGroundTruth, load_yim

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "validation" / "results"
VALIDATION_JSON = RESULTS_DIR / "validation.json"
CALIBRATION_JSON = RESULTS_DIR / "band_gap_calibration.json"

Scorer = Callable[[dict[str, LoadedGroup]], ProvenanceBundle]

# Owner's controls: ThO2 and BeO sit in the baseline oxides; the Cd and Pb compounds and BeO
# are the Yim fixture's negatives and are checked on the Yim run.
BASELINE_NEGATIVE_CONTROLS = ["ThO2", "BeO"]


@dataclass(frozen=True)
class YimLikeRun:
    """A second scorer configuration for the Yim comparison, reported beside the default one.

    `description` is written into the results as given (label, weights, target band and its
    status); the scorer must produce a bundle whose config sha reflects the overrides."""

    score: Scorer
    description: dict[str, Any]


def yim_like_block(
    run: YimLikeRun, groups: dict[str, LoadedGroup], gt: YimGroundTruth
) -> dict[str, Any]:
    bundle = run.score(groups)
    return {
        **run.description,
        "config_sha": bundle.run.config_sha,
        "note": bundle.run.note,
        "tables": [asdict(yim_table(bundle, gt, t)) for t in gt.tables()],
    }


def git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, cwd=ROOT
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def run_validation(
    score: Scorer,
    *,
    scorer_name: str,
    out_dir: Path = RESULTS_DIR,
    yim_like: YimLikeRun | None = None,
) -> dict[str, Any]:
    spec = load_compositions()
    snapshots = load_snapshots()
    groups = load_groups(snapshots=snapshots)
    gt = load_yim()

    yim_keys = set(gt.compositions())
    yim_groups = {k: g for k, g in groups.items() if k in yim_keys}
    yim_bundle = score(yim_groups)
    baseline = {k: g for k, g in groups.items() if g.display in spec["groups"]["baseline_oxides"]}
    baseline_bundle = score(baseline)

    known, k, source = load_known_dielectrics()
    calibration = calibrate(baseline, snapshots)
    report: dict[str, Any] = {
        "scorer": {
            "name": scorer_name,
            "config_sha": yim_bundle.run.config_sha,
            "profile_name": yim_bundle.run.profile_name,
            "profile_version": yim_bundle.run.profile_version,
            "note": yim_bundle.run.note,
        },
        "inputs": {
            "git_commit": git_commit(),
            "cassette_manifest": str(cassette_manifest_path().relative_to(ROOT)),
            "snapshot_shas": snapshots.shas(),
            "yim_fixture_sha256": gt.fixture_sha256,
            "compositions_total": len(groups),
            "yim_compositions": len(yim_keys),
            "baseline_oxides": sorted(baseline),
        },
        "yim": yim_report(yim_bundle, gt).to_dict(),
        "yim_like": None if yim_like is None else yim_like_block(yim_like, yim_groups, gt),
        "recall": recall_at_k(baseline_bundle, known, k, source).to_dict(),
        "negative_controls": {
            "yim_set": asdict(negative_controls(yim_bundle, list(gt.negatives))),
            "baseline_oxides": asdict(
                negative_controls(baseline_bundle, BASELINE_NEGATIVE_CONTROLS)
            ),
        },
        "calibration_sha256": calibration.data_sha256,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / VALIDATION_JSON.name).write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    (out_dir / CALIBRATION_JSON.name).write_text(
        json.dumps(calibration.to_dict(), indent=1, sort_keys=True) + "\n"
    )
    return report
