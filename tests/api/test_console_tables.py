"""UI audit: the console's tables show page text, not Python literals or empty reasons."""

from materials_triage.api import admin
from materials_triage.cli import wiring
from materials_triage.config import schema as cs
from materials_triage.scoring.profile import load_hazard_policy


def test_hazard_table_has_no_boolean_symbol_and_no_empty_reason() -> None:
    rows = admin.hazard_rows(load_hazard_policy(cs.default_paths()["hazard_policy"]))
    subjects = [r.subject for r in rows]
    assert "False" not in subjects and "No" in subjects
    by = {r.subject: r for r in rows}
    for comp in ("BaO", "HgO", "PbO"):
        assert by[comp].reason and by[comp].reason.startswith("PubChem CID"), comp
    assert by["PbO"].reason == "PubChem CID 14827: GHS H360"


def test_layer_table_reads_as_text() -> None:
    rows = {r.key: r for r in admin.layer_rows(wiring.load_layers("oxide_dielectric_thin_film"))}
    radio = rows["exclude_radioactive"]
    assert radio.effective == "yes" and radio.site in ("locked: yes", "locked: no")
    assert all("True" not in (v or "") for r in rows.values() for v in (r.core, r.effective))
    # no layer sets the gap window in this profile: "profile" would name a layer holding nothing
    assert rows["band_gap_min_ev"].set_by == "not set"
