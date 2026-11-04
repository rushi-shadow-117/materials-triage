"""A stored run is written atomically: a concurrent reader never sees an empty or partial
file (the API's status route polled a run file while the worker was still writing it)."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from materials_triage.cli.runs import RunStore
from materials_triage.records.bundle import ProvenanceBundle

SAMPLE = Path(__file__).resolve().parents[2] / "fixtures" / "bundles" / "sample_bundle.json"


def test_save_replaces_the_file_in_one_step(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    bundle = ProvenanceBundle.model_validate(json.loads(SAMPLE.read_text()))
    store = RunStore(tmp_path / "runs")
    seen: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src, dst, *a, **k):  # type: ignore[no-untyped-def]
        seen.append((Path(src).name, Path(dst).name))
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", spy)
    path = store.save(bundle)
    assert seen and seen[-1][1] == path.name and seen[-1][0].endswith(".tmp")
    assert sorted(p.name for p in store.root.iterdir()) == [path.name]  # no temp file left
    assert store.load(str(bundle.run.run_id)).run.run_id == bundle.run.run_id


def test_a_reader_during_a_save_sees_the_old_file_or_the_new_one(tmp_path: Path) -> None:
    bundle = ProvenanceBundle.model_validate(json.loads(SAMPLE.read_text()))
    store = RunStore(tmp_path / "runs")
    store.save(bundle)
    stop = threading.Event()
    bad: list[str] = []

    def reader() -> None:
        while not stop.is_set():
            try:
                store.load(str(bundle.run.run_id))
            except Exception as e:  # noqa: BLE001 - any failure is the bug
                bad.append(repr(e))
                return

    t = threading.Thread(target=reader)
    t.start()
    for _ in range(25):
        store.save(bundle)
    stop.set()
    t.join()
    assert bad == []
