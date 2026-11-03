"""Completed bundles live as JSON files under <data_cache_dir>/runs/<run_id>.json (owner
decision, 2026-11-02). The CLI, replay, diff, and export read them by run id."""

from __future__ import annotations

from pathlib import Path

from materials_triage.records.bundle import ProvenanceBundle


class RunNotFoundError(FileNotFoundError):
    pass


class RunStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.json"

    def save(self, bundle: ProvenanceBundle) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(str(bundle.run.run_id))
        path.write_text(bundle.model_dump_json(indent=1) + "\n")
        return path

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
