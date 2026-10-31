"""Recorded fixtures must never carry credentials or raw key material."""

import json
import re
from pathlib import Path

import yaml

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Request header names that carry credentials, compared case-insensitively.
CREDENTIAL_HEADERS = {"x-api-key", "authorization"}
# Query parameters that carry credentials or contact details.
CREDENTIAL_PARAMS = re.compile(r"[?&](api_key|mailto)=", re.IGNORECASE)


def _requests() -> list[tuple[str, dict]]:
    out = []
    for path in FIXTURES.rglob("*.yaml"):
        cassette = yaml.safe_load(path.read_text())
        for interaction in cassette.get("interactions", []):
            out.append((str(path.relative_to(FIXTURES)), interaction["request"]))
    assert out
    return out


def test_no_credential_request_headers() -> None:
    offenders = [
        (path, name)
        for path, req in _requests()
        for name in (req.get("headers") or {})
        if name.lower() in CREDENTIAL_HEADERS
    ]
    assert offenders == []


def test_no_credential_query_parameters() -> None:
    offenders = [
        (path, req["uri"]) for path, req in _requests() if CREDENTIAL_PARAMS.search(req["uri"])
    ]
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
