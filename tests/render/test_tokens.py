"""Template tokens resolve against the bundle index and nothing else."""

from pathlib import Path

import pytest

from materials_triage.records.bundle import ProvenanceBundle
from materials_triage.render import tokens

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"


@pytest.fixture(scope="module")
def bundle() -> ProvenanceBundle:
    return ProvenanceBundle.model_validate_json(SAMPLE.read_text())


@pytest.fixture(scope="module")
def index(bundle: ProvenanceBundle) -> tokens.BundleIndex:
    return tokens.BundleIndex.build(bundle)


def test_index_holds_every_id_shape_the_bundle_carries(index: tokens.BundleIndex) -> None:
    assert "mp-352" in index.ids
    assert "https://openalex.org/W2024600253" in index.ids and "W2024600253" in index.ids
    assert "CID:292779" in index.ids
    assert "https://doi.org/10.1063/1.4919135" in index.ids
    assert "10.1063/1.4919135" in index.ids
    assert "expt_gap:3:HfO2" in index.ids
    assert "mp-999999" not in index.ids


def test_each_token_kind_resolves(index: tokens.BundleIndex) -> None:
    r = lambda kind, arg, **kw: tokens.resolve(index, kind, arg, **kw)  # noqa: E731
    assert r("formula", "HfO2") == "HfO2"
    assert r("rank", "HfO2") == "1="  # tied with Al2O3 at the shown precision
    assert r("rank", "ThO2") == "excluded"
    assert r("rank", "SiO2") == "would place 1st of 9, above Al2O3"
    assert r("value", "HfO2:band_gap") == "5.55 eV"
    assert r("value", "HfO2:band_gap", units="meV") == "5550 meV"
    assert r("value", "HfO2:stability") == "0.000 eV/atom"
    assert r("value", "HfO2:hazard") == "missing (not reported)"
    assert r("source", "HfO2:band_gap") == "experimental_median"
    assert r("criterion", "band_gap") == "band gap"
    assert r("count", "HfO2:polymorphs") == "15"
    assert r("count", "HfO2:hits") == "5"
    assert r("count", "HfO2:matched") == "3496"
    assert r("ghs", "HfO2") == (
        "hazard codes reported in 7 of 344 reports (codes not listed in the record); "
        "337 report not classified"
    )
    assert r("ghs", "SiO2").startswith("GHS codes H315, H319") and "of 9127 reports" in r(
        "ghs", "SiO2"
    )
    assert r("spacegroup", "HfO2") == "P2_1/c"
    assert r("id", "mp-352") == "mp-352"


def test_unknown_tokens_raise_with_the_verifier_failure_kind(index: tokens.BundleIndex) -> None:
    with pytest.raises(tokens.TokenError) as e:
        tokens.resolve(index, "formula", "PbO")
    assert e.value.kind == "formula_not_in_bundle"
    with pytest.raises(tokens.TokenError) as e:
        tokens.resolve(index, "id", "mp-999999")
    assert e.value.kind == "unknown_record_id"
    with pytest.raises(tokens.TokenError) as e:
        tokens.resolve(index, "criterion", "vibes")
    assert e.value.kind == "unknown_token"
    with pytest.raises(tokens.TokenError) as e:
        tokens.resolve(index, "value", "HfO2")
    assert e.value.kind == "unknown_token"


def test_render_text_fills_every_token(index: tokens.BundleIndex) -> None:
    text = "{formula:HfO2} ranks {rank:HfO2} with a gap of {value:HfO2:band_gap}."
    assert tokens.render_text(index, text) == "HfO2 ranks 1= with a gap of 5.55 eV."
    with pytest.raises(tokens.TokenError):
        tokens.render_text(index, "{formula:Unobtainium}")
