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
    assert (f".{path.name}.{os.getpid()}.tmp", path.name) in seen
    assert all(src.endswith(".tmp") for src, _ in seen)  # the summary index is atomic too
    files = sorted(p.name for p in store.root.iterdir() if p.is_file())
    assert files == [path.name]  # no temp file left
    assert sorted(p.name for p in (store.root / "index").iterdir()) == [path.name]
    assert [p.name for p in store.list()] == [path.name]  # the index is not a run


def test_the_history_summary_reads_without_the_bundle(tmp_path: Path) -> None:
    """UI audit: the history list parsed every bundle (tens of megabytes for a discovery run)
    and sat on "Loading" for seconds; it now reads a small index written on save."""
    bundle = ProvenanceBundle.model_validate(json.loads(SAMPLE.read_text()))
    store = RunStore(tmp_path / "runs")
    store.save(bundle)
    run_id = str(bundle.run.run_id)
    expected = store.summary(run_id)
    assert expected["ranked"] == len(bundle.ranked())
    assert expected["profile"] == bundle.run.profile_name
    # an older bundle with no index entry still lists, and gains one
    (store.root / "index" / f"{run_id}.json").unlink()
    assert store.summary(run_id) == expected
    assert (store.root / "index" / f"{run_id}.json").exists()
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
