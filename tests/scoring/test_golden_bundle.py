"""The scored bundle regenerates byte-identical from cassettes and config."""

import json
from pathlib import Path

from scripts import build_scored_bundle

from materials_triage.records.bundle import ProvenanceBundle

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "bundles" / "scored_bundle.json"


def test_scored_bundle_is_current_and_well_formed(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "scored_bundle.json"
    monkeypatch.setattr(build_scored_bundle, "OUT", out)
    assert build_scored_bundle.main() == 0
    assert out.read_text() == GOLDEN.read_text(), "run scripts/build_scored_bundle.py"
    bundle = ProvenanceBundle.model_validate_json(GOLDEN.read_text())
    assert bundle.bundle_version == 2 and "Track A scorer" in (bundle.run.note or "")
    assert [c.rank for c in bundle.ranked()] == list(range(1, 9))
    for row in [*bundle.candidates, *bundle.anchors]:
        assert row.score is not None
        for c in row.score.criteria:
            if not c.missing:
                assert c.normalized is not None and 0.0 <= c.normalized <= 1.0
                if c.criterion not in ("simplicity", "hazard"):
                    assert c.provenance is not None, (row.composition, c.criterion)
            else:
                assert c.contribution == 0.0 and c.missing_reason
        for p in row.group.polymorphs.top_by_hull:
            if p.hull_energy is not None:
                assert p.hull_energy.value is not None or p.hull_energy.missing_reason is not None
    raw = json.loads(GOLDEN.read_text())
    assert raw["run"]["run_id"] == "00000000-0000-4000-8000-000000000002"
