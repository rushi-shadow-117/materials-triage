"""Load every adapter cassette into the provenance store so evals can run in replay mode.

Usage:
    uv run python scripts/seed_store_from_cassettes.py [--root fixtures/adapters]

Each recorded interaction becomes a raw_responses row (deduplicated by body hash) with a
fetch_events row in mode "seed". Credentials were stripped at recording time, so the stored
params never contain them. Idempotent: re-running adds fetch events, never duplicates bodies.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import yaml

from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.provenance.store import Store, make_engine
from materials_triage.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BY_DIR = {
    "mp": Source.MP,
    "openalex": Source.OPENALEX,
    "pubchem": Source.PUBCHEM,
    "oqmd": Source.OQMD,
    "cod": Source.COD,
}
AUTH_BY_SOURCE = {Source.MP: "mp_header", Source.OPENALEX: "openalex_param"}


def call_from_uri(source: Source, uri: str) -> Call:
    parts = urlsplit(uri)
    params = {
        k: v
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in {"api_key", "mailto"}
    }
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    endpoint = parts.path.strip("/").replace("rest/", "").replace("optimade/v1/", "")
    auth = AUTH_BY_SOURCE.get(source, "none")
    return Call(source=source, endpoint=endpoint, url=url, params=params, auth=auth)  # type: ignore[arg-type]


def iter_raw(root: Path):  # type: ignore[no-untyped-def]
    for path in sorted(root.rglob("*.yaml")):
        source = SOURCE_BY_DIR.get(path.parent.name)
        if source is None:
            continue
        cassette = yaml.safe_load(path.read_text())
        for i in cassette.get("interactions", []):
            resp = i["response"]
            body = resp["body"]["string"]
            body_bytes = body.encode() if isinstance(body, str) else bytes(body)
            headers = {k.lower(): v for k, v in (resp.get("headers") or {}).items()}
            ctype = (headers.get("content-type") or [None])[0]
            recorded = i.get("recorded_at")
            fetched = (
                datetime.fromisoformat(recorded.replace("GMT", "+00:00"))
                if isinstance(recorded, str) and "T" in recorded
                else datetime.now(UTC)
            )
            yield (
                path,
                RawResponse(
                    call=call_from_uri(source, i["request"]["uri"]),
                    status=int(resp["status"]["code"]),
                    body=body_bytes,
                    content_type=ctype,
                    fetched_at=fetched,
                ),
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "fixtures" / "adapters"))
    args = ap.parse_args()
    store = Store(make_engine(Settings().database_url))
    new = seen = 0
    for _path, raw in iter_raw(Path(args.root)):
        _, was_new = store.put_raw(raw, mode="seed")
        new += int(was_new)
        seen += 1
    print(f"seeded {seen} interactions, {new} new raw bodies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
