"""vcr configuration shared by the adapter tests and the recording scripts.

Credentials are stripped from recorded requests: the MP header and the OpenAlex query
parameters. Matching ignores headers so replays do not depend on client versions.
"""

from __future__ import annotations

from pathlib import Path

import vcr

ROOT = Path(__file__).resolve().parents[3]
ADAPTER_CASSETTES = ROOT / "fixtures" / "adapters"


def make_vcr(record_mode: str = "none") -> vcr.VCR:
    return vcr.VCR(
        record_mode=record_mode,
        filter_headers=["X-API-KEY", "x-api-key", "X-Api-Key", "Authorization", "authorization"],
        filter_query_parameters=["api_key", "mailto"],
        match_on=["method", "scheme", "host", "port", "path", "query"],
        decode_compressed_response=True,
    )


def cassette_path(source: str, name: str) -> Path:
    path = ADAPTER_CASSETTES / source / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
