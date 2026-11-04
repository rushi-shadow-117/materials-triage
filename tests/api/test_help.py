"""The in-app help routes (Track H item 2): the guides come from a fixed allowlist and the
key lists are the closed vocabularies."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_the_two_guides_are_served_as_markdown_and_nothing_else_is(client: TestClient) -> None:
    sci = client.get("/api/help/scientist")
    assert sci.status_code == 200
    assert sci.headers["content-type"].startswith("text/markdown")
    assert sci.text.startswith("# Scientist guide")
    adm = client.get("/api/help/admin")
    assert adm.status_code == 200 and adm.text.startswith("# Admin guide")
    for name in ("README", "DECISIONS", "..", "%2e%2e", "SCIENTIST_GUIDE.md"):
        r = client.get(f"/api/help/{name}")
        assert r.status_code == 404, name
        assert "# " not in r.text  # no document leaks; a dotted path never reaches the route
    r = client.get("/api/help/README")
    assert "use scientist or admin" in r.json()["detail"]


def test_help_keys_list_every_closed_vocabulary(client: TestClient) -> None:
    keys = client.get("/api/help/keys").json()
    expected = {"criteria", "flags", "caveats", "exclusion_rules", "evidence_tiers", "guides"}
    assert set(keys) == expected
    assert "band_gap" in keys["criteria"]
    assert "hazard_flag" in keys["flags"] and "hazard_flag" in keys["caveats"]
    assert "structure.molecular" in keys["exclusion_rules"]
    assert "unclassified" in keys["evidence_tiers"]
    assert keys["guides"] == ["scientist", "admin"]
