import json
from pathlib import Path

import pytest
import yaml

from materials_triage.adapters.mpid import to_alpha, to_legacy

WIRE = Path(__file__).resolve().parents[1] / "fixtures" / "wire" / "mp"


def test_known_pair() -> None:
    assert to_legacy("mp-aaaaaayt") == "mp-643"
    assert to_alpha("mp-643") == "mp-aaaaaayt"


def test_legacy_passes_through_and_bad_shape_raises() -> None:
    assert to_legacy("mp-352") == "mp-352"
    with pytest.raises(ValueError):
        to_legacy("not-an-id-1")


def test_every_recorded_raw_id_decodes_to_a_client_id() -> None:
    """Raw alpha ids in each summary cassette must map onto the client ids in meta.json."""
    meta = json.loads((WIRE / "meta.json").read_text())
    checked = 0
    for formula, entry in meta["materials"].items():
        if formula.startswith("_"):
            continue
        client_ids = {r["material_id"] for r in entry["detail"]["rows"]}
        cassette = yaml.safe_load((WIRE / f"{formula}.yaml").read_text())
        for interaction in cassette["interactions"]:
            if "/materials/summary/" not in interaction["request"]["uri"]:
                continue
            body = json.loads(interaction["response"]["body"]["string"])
            raw_ids = {d["material_id"] for d in body["data"]}
            if not raw_ids:
                continue
            assert {to_legacy(r) for r in raw_ids} == client_ids, formula
            checked += len(raw_ids)
    assert checked > 500
