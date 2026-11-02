"""Write the OpenAPI schema to web/src/api/openapi.json (then: npx openapi-typescript)."""

from __future__ import annotations

import json
from pathlib import Path

from materials_triage.api.openapi import openapi_schema

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "src" / "api" / "openapi.json"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(openapi_schema(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
