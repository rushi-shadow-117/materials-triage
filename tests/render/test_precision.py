"""Display precision: one table, decimal half-up rounding, every accepted rendering."""

from materials_triage.render import precision as p


def test_quantize_rounds_half_up_in_decimal_not_binary_float() -> None:
    assert p.quantize(5.55, 1) == "5.6"
    assert p.quantize(0.0095, 3) == "0.010"
    assert p.quantize(2.5, 0) == "3"
    assert p.quantize(-0.0001, 3) == "0.000"
    assert p.quantize(344, 0) == "344"


def test_fmt_uses_the_unit_places_and_suffix() -> None:
    assert p.fmt(5.55, "eV") == "5.55 eV"
    assert p.fmt(0.009928638750000829, "eV/atom") == "0.010 eV/atom"
    assert p.fmt(18.7477708, "1") == "18.7"
    assert p.fmt(2, "elements") == "2 elements"
    assert p.fmt(1.0, "score") == "1.000"
    assert p.fmt(3, "rank") == "3"


def test_fmt_converts_energies_when_the_query_asks_for_mev() -> None:
    assert p.fmt(5.55, "eV", "meV") == "5550 meV"
    assert p.fmt(0.0095, "eV/atom", "meV") == "10 meV/atom"
    assert p.fmt(2, "elements", "meV") == "2 elements"


def test_renderings_cover_every_precision_and_both_energy_units() -> None:
    r = p.renderings(5.55, "eV")
    assert {"6", "5.6", "5.55", "5550"} <= r
    assert "5.5" not in r and "5.550" not in r
    hull = p.renderings(0.0095, "eV/atom")
    assert {"0", "0.0", "0.01", "0.010", "10"} <= hull
    assert p.renderings(344, "count") == {"344"}
    assert p.renderings(2015, "year") == {"2015"}


def test_unknown_unit_falls_back_to_two_places() -> None:
    assert p.places("furlongs") == 2
    assert p.fmt(1.2345, "furlongs") == "1.23 furlongs"
