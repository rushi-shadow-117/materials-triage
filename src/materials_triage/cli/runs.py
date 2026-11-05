"""Completed bundles live as JSON files under <data_cache_dir>/runs/<run_id>.json (owner
decision, 2026-11-02). The CLI, replay, diff, and export read them by run id."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from materials_triage.records.bundle import ProvenanceBundle


class RunNotFoundError(FileNotFoundError):
    pass


class RunStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.json"

    def save(self, bundle: ProvenanceBundle) -> Path:
        """Write the bundle atomically: a reader (the API's status route, a concurrent CLI)
        sees either no file or the whole file, never an empty or half-written one."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(str(bundle.run.run_id))
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(bundle.model_dump_json(indent=1) + "\n")
        os.replace(tmp, path)
        self._write_summary(bundle)
        return path

    # A discovery bundle is tens of megabytes; the run history needs eight fields. The summary
    # sits in index/ (not matched by list()'s *.json glob) and is rebuilt from the bundle when
    # absent, so bundles written before it existed still list.
    def _summary_path(self, run_id: str) -> Path:
        return self.root / "index" / f"{run_id}.json"

    def _write_summary(self, bundle: ProvenanceBundle) -> dict[str, Any]:
        data = summarize(bundle)
        path = self._summary_path(str(bundle.run.run_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, sort_keys=True))
        os.replace(tmp, path)
        return data

    def summary(self, run_id: str) -> dict[str, Any]:
        """The run-history fields of a stored run, without parsing the bundle when possible."""
        path = self._summary_path(run_id)
        bundle_path = self.path(run_id)
        if path.exists() and (
            not bundle_path.exists() or path.stat().st_mtime >= bundle_path.stat().st_mtime
        ):
            data: dict[str, Any] = json.loads(path.read_text())
            return data
        return self._write_summary(self.load(run_id))

    def load(self, run_id: str) -> ProvenanceBundle:
        path = self.path(run_id)
        if not path.exists():
            candidates = [p for p in self.list() if p.stem.startswith(run_id)]
            if len(candidates) == 1:
                path = candidates[0]
            else:
                raise RunNotFoundError(f"no stored run {run_id!r} under {self.root}")
        return ProvenanceBundle.model_validate_json(path.read_text())

    def list(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime)


def summarize(bundle: ProvenanceBundle) -> dict[str, Any]:
    return {
        "mode": bundle.criteria.mode,
        "profile": bundle.run.profile_name,
        "request_text": bundle.criteria.request_text,
        "started_at": bundle.run.started_at.isoformat(),
        "finished_at": bundle.run.finished_at.isoformat() if bundle.run.finished_at else None,
        "partial": bundle.run.partial,
        "ranked": len(bundle.ranked()),
        "excluded": len(bundle.excluded()),
    }
