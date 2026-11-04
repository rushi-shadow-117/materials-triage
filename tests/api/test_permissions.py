"""docs/PERMISSIONS.md is checked against the app: every route it lists exists with the named
dependency, every app route is listed, and the role columns match what the dependency admits."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute

from materials_triage.api import auth
from materials_triage.api.app import app

DOC = Path(__file__).resolve().parents[2] / "docs" / "PERMISSIONS.md"
ADMITS = {
    "any_role": {"scientist", "fde", "admin"},
    "console_roles": {"fde", "admin"},
    "admin_only": {"admin"},
    "current_principal": {"scientist", "fde", "admin"},
    "none (no identity needed)": {"scientist", "fde", "admin"},
}
DEPENDENCY_NAMES = {
    id(auth.any_role): "any_role",
    id(auth.console_roles): "console_roles",
    id(auth.admin_only): "admin_only",
    id(auth.current_principal): "current_principal",
}


def _doc_rows() -> dict[tuple[str, str], tuple[set[str], str]]:
    rows: dict[tuple[str, str], tuple[set[str], str]] = {}
    section = DOC.read_text().split("## API routes", 1)[1].split("## Screen actions", 1)[0]
    for line in section.splitlines():
        m = re.match(r"\| (GET|POST) (\S+) \| (yes|no) \| (yes|no) \| (yes|no) \| ([^|]+) \|", line)
        if not m:
            continue
        method, path, sci, fde, adm, dep = m.groups()
        allowed = {r for r, v in (("scientist", sci), ("fde", fde), ("admin", adm)) if v == "yes"}
        rows[(method, path)] = (allowed, dep.strip())
    return rows


def _api_routes(routes: list[Any]) -> list[APIRoute]:
    """Every APIRoute, including those of included routers (FastAPI keeps an included router
    as one nested route that exposes `original_router`)."""
    out: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            out.append(route)
        elif hasattr(route, "original_router"):
            out.extend(_api_routes(route.original_router.routes))
    return out


def _app_routes() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for route in _api_routes(app.routes):
        names = [
            DEPENDENCY_NAMES.get(id(d.call), "?")
            for d in route.dependant.dependencies
            if d.call is not None
        ]
        # a role dependency wraps current_principal; the outermost one is the rule
        name = next((n for n in names if n in ("any_role", "console_roles", "admin_only")), None)
        if name is None:
            name = (
                "current_principal" if "current_principal" in names else "none (no identity needed)"
            )
        for method in route.methods or set():
            if method in ("GET", "POST"):
                out[(method, route.path)] = name
    return out


def test_permission_matrix_matches_the_app() -> None:
    doc = _doc_rows()
    routes = _app_routes()
    assert len(routes) == 24 and all(path.startswith("/api/") for _m, path in routes)
    assert set(doc) == set(routes), {
        "only in doc": sorted(set(doc) - set(routes)),
        "only in app": sorted(set(routes) - set(doc)),
    }
    for key, (allowed, dep) in doc.items():
        assert routes[key] == dep, f"{key}: doc says {dep}, app has {routes[key]}"
        assert ADMITS[dep] == allowed, f"{key}: {dep} admits {ADMITS[dep]}, doc lists {allowed}"
