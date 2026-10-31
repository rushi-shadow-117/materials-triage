"""Recorded fixtures must never carry credentials or raw key material."""

import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Header names vcrpy is configured to strip, plus the query parameters that carry keys.
FORBIDDEN = re.compile(r"(x-api-key|authorization|api_key=|mailto=)", re.IGNORECASE)


def test_no_credentials_in_cassettes() -> None:
    offenders = []
    for path in FIXTURES.rglob("*.yaml"):
        if FORBIDDEN.search(path.read_text()):
            offenders.append(str(path.relative_to(FIXTURES)))
    assert offenders == []


def test_every_recorded_source_has_meta() -> None:
    for src_dir in (FIXTURES / "wire").iterdir():
        if src_dir.is_dir():
            meta = json.loads((src_dir / "meta.json").read_text())
            assert meta["source"] == src_dir.name
            assert meta["materials"]


def test_snapshot_manifest_pins_hashes() -> None:
    manifest = json.loads((FIXTURES / "snapshots" / "MANIFEST.json").read_text())
    for name, entry in manifest["snapshots"].items():
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]), name
        assert (FIXTURES / "snapshots" / f"{name}.slice.json").exists(), name
