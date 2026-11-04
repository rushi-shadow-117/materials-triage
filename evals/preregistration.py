"""Pre-registration: record what the scorer and data looked like before validation runs, so a
later tuning cannot pass as the original. The report shows both shas when they differ."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evals.execute import config_files_sha, effective_config_sha
from materials_triage.config.schema import default_paths

ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = ROOT / "evals" / "preregistration.json"
YIM = ROOT / "fixtures" / "validation" / "yim2015.yaml"
KNOWN = ROOT / "fixtures" / "validation" / "known_dielectrics.yaml"
MANIFEST = ROOT / "fixtures" / "adapters" / "recording_manifest.json"
SNAPSHOTS = ROOT / "fixtures" / "snapshots" / "MANIFEST.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, cwd=ROOT
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def current_state() -> dict[str, Any]:
    paths = default_paths()
    profile = yaml.safe_load(paths["scoring_profile"].read_text())
    policy = yaml.safe_load(paths["hazard_policy"].read_text())
    snapshots = json.loads(SNAPSHOTS.read_text())["snapshots"]
    return {
        "config_sha": effective_config_sha(),
        "config_files": config_files_sha(),
        "profile_name": str(profile.get("profile")),
        "profile_version": str(profile.get("version", "0")),
        "hazard_policy_version": str(policy.get("schema_version", 0)),
        "yim_fixture_sha256": _sha(YIM),
        "known_dielectrics_sha256": _sha(KNOWN),
        "cassette_manifest_sha256": _sha(MANIFEST),
        "snapshot_shas": {k: v["sha256"] for k, v in snapshots.items()},
        "git_commit": git_commit(),
    }


INITIAL_LABEL = "initial (Track E)"


def load_entries(path: Path = PREREG_PATH) -> list[dict[str, Any]]:
    """Every pre-registration, oldest first. A file written before entries existed holds one
    bare record, read as the initial entry."""
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "entries" in data:
        return list(data["entries"])
    return [{"label": INITIAL_LABEL, **data}]


def preregister(
    path: Path = PREREG_PATH, *, scorer_name: str, label: str = INITIAL_LABEL
) -> dict[str, Any]:
    """Append a pre-registration entry; earlier entries are kept unchanged."""
    record = {
        "label": label,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scorer": scorer_name,
        **current_state(),
    }
    entries = load_entries(path) + [record]
    path.write_text(json.dumps({"entries": entries}, indent=1, sort_keys=True) + "\n")
    return record


def compare(path: Path = PREREG_PATH) -> dict[str, Any] | None:
    """None when nothing is pre-registered; otherwise the latest entry's shas against the
    current state, and the history of every entry."""
    entries = load_entries(path)
    if not entries:
        return None
    rec = entries[-1]
    now = current_state()
    changed_files = sorted(
        p
        for p in set(rec["config_files"]) | set(now["config_files"])
        if rec["config_files"].get(p) != now["config_files"].get(p)
    )
    return {
        "label": rec.get("label", INITIAL_LABEL),
        "recorded_at": rec["recorded_at"],
        "scorer": rec["scorer"],
        "preregistered_config_sha": rec["config_sha"],
        "current_config_sha": now["config_sha"],
        "config_tuned_after_preregistration": rec["config_sha"] != now["config_sha"],
        "config_files_changed": changed_files,
        "data_unchanged": all(
            rec[k] == now[k]
            for k in ("yim_fixture_sha256", "cassette_manifest_sha256", "snapshot_shas")
        ),
        "preregistered_commit": rec["git_commit"],
        "history": [
            {
                "label": e.get("label", INITIAL_LABEL),
                "recorded_at": e["recorded_at"],
                "git_commit": e["git_commit"],
                "config_sha": e["config_sha"],
            }
            for e in entries
        ],
    }
