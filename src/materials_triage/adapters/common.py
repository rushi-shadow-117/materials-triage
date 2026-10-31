"""Helpers shared by adapters: formula normalization, value construction, provenance."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pymatgen.core.composition import Composition

from materials_triage.adapters.base import RawResponse
from materials_triage.records import MissingReason, Provenance, Value

NA_SENTINELS = {"na", "n/a", "none", "null", ""}


def reduced_formula(formula: str) -> str:
    """Canonical composition key. Raises on strings pymatgen cannot parse."""
    return str(Composition(formula).reduced_formula)


def try_reduced_formula(formula: str) -> str | None:
    try:
        return reduced_formula(formula)
    except Exception:  # noqa: BLE001 - unparsable formula is data, not a crash
        return None


def num_or_none(x: Any) -> tuple[float | None, MissingReason | None]:
    """Coerce a source value to float. Zero is a value. Sentinels and absences are missing."""
    if x is None:
        return None, MissingReason.ABSENT
    if isinstance(x, bool):
        return float(x), None
    if isinstance(x, int | float):
        return float(x), None
    if isinstance(x, str):
        if x.strip().lower() in NA_SENTINELS:
            return None, MissingReason.NA_SENTINEL
        try:
            return float(x), None
        except ValueError:
            return None, MissingReason.NA_SENTINEL
    return None, MissingReason.ABSENT


def int_or_none(x: Any) -> int | None:
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, str) and x.strip().isdigit():
        return int(x)
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return None


def provenance(
    raw: RawResponse,
    *,
    source_record_id: str,
    raw_id: UUID | None = None,
    url: str | None = None,
    license: str | None = None,
) -> Provenance:
    return Provenance(
        source=str(raw.call.source),
        source_record_id=source_record_id,
        raw_response_id=raw_id,
        raw_sha256=raw.sha256,
        fetched_at=raw.fetched_at,
        source_version=raw.source_version,
        url=url,
        license=license if license is not None else raw.license,
    )


def value_from(x: Any, *, unit: str, method: str | None, prov: Provenance) -> Value[float]:
    v, reason = num_or_none(x)
    return Value[float](value=v, unit=unit, method=method, missing_reason=reason, provenance=prov)
