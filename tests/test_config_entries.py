"""Every config entry carries a status, attribution, and a source consistent with its status."""

from pathlib import Path
from typing import Any

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"
STATUSES = {"entered", "pending_verification", "pending_signoff", "open"}


def _entries(node: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    """Yield every mapping that carries a `status` key, with a readable path."""
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        if "status" in node:
            found.append((path, node))
        for k, v in node.items():
            found.extend(_entries(v, f"{path}/{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found.extend(_entries(v, f"{path}[{i}]"))
    return found


def _all_entries() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for f in sorted(CONFIG.rglob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        assert data.get("schema_version") == 0, f
        out.extend(_entries(data, f.name))
    assert out
    return out


def test_statuses_are_known() -> None:
    bad = [(p, e["status"]) for p, e in _all_entries() if e["status"] not in STATUSES]
    assert bad == []


def test_entered_values_have_a_located_source() -> None:
    """An `entered` entry that carries a value must point at a URL or be a declared decision."""
    bad = []
    for path, e in _all_entries():
        if e["status"] != "entered":
            continue
        src = e.get("source")
        if src is None:
            continue  # nested entries (for example additional_sources) carry their own
        if src.get("url") is None and src.get("access") != "not_applicable":
            bad.append(path)
    assert bad == []


def test_open_entries_carry_no_value() -> None:
    bad = []
    for path, e in _all_entries():
        if e["status"] == "open" and any(
            e.get(k) is not None for k in ("value", "value_range", "cutoff_ev_per_atom")
        ):
            bad.append(path)
    assert bad == []


def test_top_level_entries_are_attributed() -> None:
    bad = []
    for path, e in _all_entries():
        carries_content = any(k in e for k in ("source", "value", "elements", "items"))
        if carries_content and not (e.get("entered_by") and e.get("entered_on")):
            bad.append(path)
    # additional_sources items are attributed by their parent entry
    bad = [p for p in bad if "additional_sources" not in p and "evidence" not in p]
    assert bad == []
