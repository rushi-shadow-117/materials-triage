"""COD over OPTIMADE. Recorded 2026-10-31 after 20:43 UTC, the first time COD answered all day."""

from materials_triage.adapters import optimade
from materials_triage.adapters.transport import HttpxTransport


def test_cod_filters_by_elements_not_formula() -> None:
    assert optimade.optimade_filter("cod", "ThO2") == 'elements HAS ALL "O","Th" AND nelements=2'
    assert optimade.optimade_filter("oqmd", "ThO2") == 'chemical_formula_reduced="O2Th"'


def test_cod_info_structures_lists_properties(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    with cassette("cod", "info_structures"):
        raw = transport.get(optimade.plan_info("cod"))
    assert raw.status == 200
    body = raw.json()
    props = body["data"]["properties"]
    assert "chemical_formula_reduced" in props and "_cod_sgnumber" in props
    assert "space_group_it_number" not in props
    assert body.get("meta", {}).get("api_version", "").startswith("1.")


def test_cod_tho2_structures(transport: HttpxTransport, cassette) -> None:  # type: ignore[no-untyped-def]
    with cassette("cod", "structures_ThO2"):
        raw = transport.get(optimade.plan_structures("cod", "ThO2", page_limit=10))
    returned, _more, _next = optimade.page_info(raw)
    recs = optimade.records(raw, "cod", formula="ThO2")
    assert raw.status == 200 and returned is not None and returned >= 1
    assert recs and all(r.composition == "ThO2" for r in recs)
    # COD fills _cod_sg ("F m -3 m") but not _cod_sgnumber here; the number is derived.
    assert all(r.payload["space_group_it_number"] == 225 for r in recs)
    assert all(r.payload["space_group_source"] == "derived_from_symbol" for r in recs)
    assert all(r.provenance.source == "cod" and r.provenance.raw_sha256 == raw.sha256 for r in recs)


def test_cod_elements_query_is_post_filtered_to_the_formula(
    transport: HttpxTransport, cassette
) -> None:  # type: ignore[no-untyped-def]
    with cassette("cod", "structures_TiO2"):
        raw = transport.get(optimade.plan_structures("cod", "TiO2", page_limit=10))
    returned, more, _ = optimade.page_info(raw)
    assert raw.status == 200 and returned is not None and returned > 10 and more is True
    everything = optimade.records(raw, "cod")
    only_tio2 = optimade.records(raw, "cod", formula="TiO2")
    assert len(only_tio2) <= len(everything)
    assert all(r.composition == "TiO2" for r in only_tio2)
