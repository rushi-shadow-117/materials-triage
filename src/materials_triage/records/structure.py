"""Structural dimensionality of a crystal structure, computed in code.

The method is Larsen et al., "Definition of a scoring parameter to identify low-dimensional
materials components", npj Comput Mater 5, 26 (2019), as implemented by
`pymatgen.analysis.dimensionality.get_dimensionality_larsen`. That function needs a bonded
structure; bonds come from pymatgen's CrystalNN with its defaults (docs/DECISIONS.md, Track G).
A value of 0 means the structure is made of isolated clusters (molecules); 3 is a fully
connected network. Pure and deterministic for a given structure.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any

from materials_triage.records import CompositionGroup, MissingReason, Polymorph, Value

METHOD = "larsen2019_crystalnn"


def larsen_dimensionality(structure: dict[str, Any]) -> int:
    from pymatgen.analysis.dimensionality import get_dimensionality_larsen
    from pymatgen.analysis.local_env import CrystalNN
    from pymatgen.core.structure import Structure

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s = Structure.from_dict(structure)
        bonded = CrystalNN().get_bonded_structure(s)  # type: ignore[no-untyped-call]
        return int(get_dimensionality_larsen(bonded))  # type: ignore[no-untyped-call]


def dimensionality_value(record: Any) -> Value[int]:
    """A Value from an `mp_structure` SourceRecord; a structure that cannot be analysed is
    missing (not_computed), never guessed."""
    structure = record.payload.get("structure")
    if not isinstance(structure, dict):
        return Value[int](
            value=None,
            unit="1",
            method=METHOD,
            missing_reason=MissingReason.ABSENT,
            provenance=record.provenance,
        )
    try:
        dim = larsen_dimensionality(structure)
    except Exception:  # noqa: BLE001 - an unanalysable structure is missing, with its record
        return Value[int](
            value=None,
            unit="1",
            method=METHOD,
            missing_reason=MissingReason.NOT_COMPUTED,
            provenance=record.provenance,
        )
    return Value[int](value=dim, unit="1", method=METHOD, provenance=record.provenance)


def attach_dimensionality(
    group: CompositionGroup,
    target: Polymorph | None,
    fetch_records: Callable[[str], list[Any]],
) -> None:
    """Set `dimensionality` on `target` (the polymorph the scorer will score) from its MP
    structure. `fetch_records(mp_id)` returns the mp_structure records for that id, or []
    when the structure is not available; the polymorph then keeps None."""
    if target is None or target.ids.mp is None:
        return
    records = [r for r in fetch_records(target.ids.mp) if r.source_record_id == target.ids.mp]
    if not records:
        return
    target.dimensionality = dimensionality_value(records[0])
    del group  # the polymorph object is shared with the group's list
