"""Display precision, the single source of truth for rounding.

Renderers format every number through `fmt`; the verifier accepts a written number only if it
equals one of `renderings` for some bundle value. Both read the same table, so a renderer can
never emit a string the verifier rejects. Arithmetic is decimal, rounding half up, so the
accepted strings do not depend on binary float representation.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

PLACES: dict[str, int] = {
    "eV": 2,
    "meV": 0,
    "eV/atom": 3,
    "meV/atom": 0,
    "1": 1,  # dimensionless (dielectric constant)
    "elements": 0,
    "abstracts": 0,
    "count": 0,
    "rank": 0,
    "year": 0,
    "score": 3,
}
DEFAULT_PLACES = 2
ENERGY_TO_MEV: dict[str, str] = {"eV": "meV", "eV/atom": "meV/atom"}
NO_SUFFIX: frozenset[str] = frozenset({"1", "count", "rank", "year", "score"})


def places(unit: str | None) -> int:
    return PLACES.get(unit or "", DEFAULT_PLACES)


def quantize(value: float | int | Decimal, d: int) -> str:
    """`value` rounded half up to `d` decimal places, as the string a user sees."""
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    q = dec.quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    text = f"{q:f}"
    if text.startswith("-") and set(text[1:]) <= {"0", "."}:
        text = text[1:]
    return text


def display_unit(unit: str | None, units_setting: str = "eV") -> tuple[Decimal, str | None]:
    """(factor, label) for showing `unit` under the query's units setting."""
    if units_setting == "meV" and unit in ENERGY_TO_MEV:
        return Decimal(1000), ENERGY_TO_MEV[unit]
    return Decimal(1), unit


def fmt_number(value: float | int, unit: str | None, units_setting: str = "eV") -> str:
    factor, label = display_unit(unit, units_setting)
    return quantize(Decimal(str(value)) * factor, places(label))


def fmt(value: float | int, unit: str | None, units_setting: str = "eV") -> str:
    """Number plus unit suffix, e.g. "5.55 eV", "2 elements", "18.7" (dimensionless)."""
    factor, label = display_unit(unit, units_setting)
    number = quantize(Decimal(str(value)) * factor, places(label))
    if label is None or label in NO_SUFFIX:
        return number
    return f"{number} {label}"


def renderings(value: float | int, unit: str | None) -> set[str]:
    """Every string a user could legitimately write for `value`: each precision from zero
    places up to the unit's display places, in the stored unit and, for energies, in meV."""
    out: set[str] = set()
    dec = Decimal(str(value))
    forms: list[tuple[str | None, Decimal]] = [(unit, Decimal(1))]
    if unit in ENERGY_TO_MEV:
        forms.append((ENERGY_TO_MEV[unit], Decimal(1000)))
    for label, factor in forms:
        for d in range(places(label) + 1):
            out.add(quantize(dec * factor, d))
    return out
