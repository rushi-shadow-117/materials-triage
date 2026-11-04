"""Record what an eval case's pipeline run asks for and the cassettes do not hold.

The run goes through the real pipeline (evals PipelineExecutor, scripted fake LLM). Every
fetch is served from fixtures/adapters first; a miss goes to the live API once and is
written to fixtures/adapters/<source>/run_<case>.yaml in the cassette format the replay
readers use (request uri without keys, status, content type, body, recorded_at). Discovery
pages are recorded the same way, so the cassettes hold exactly the calls a run makes.

Owner rule (Track F): at most two live rounds per case. A round is one run with live fill;
after each round the case is replayed with no network, and any "enrichment unavailable" or
"no stored response" left after round two is printed and left for the report.

    uv run python scripts/record_case_gaps.py A1 B1 B2
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import yaml
from evals.cases import load_cases
from evals.execute import PipelineExecutor

from materials_triage.adapters.base import Call, RawResponse
from materials_triage.adapters.transport import TIMEOUT, USER_AGENT, HttpxTransport
from materials_triage.cli import wiring
from materials_triage.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / "fixtures" / "adapters"
DIR_BY_SOURCE = {v: k for k, v in wiring.SOURCE_BY_DIR.items()}
MAX_ROUNDS = 2


def uri_for(call: Call) -> str:
    return f"{call.url}?{urlencode(sorted(call.params.items()))}" if call.params else call.url


class LiveFill:
    """Cassettes first; a miss is fetched live and kept for writing."""

    def __init__(self, transport: HttpxTransport) -> None:
        self.cassettes = wiring.CassetteFetch()
        self.transport = transport
        self.new: list[RawResponse] = []

    def __call__(self, call: Call) -> RawResponse | None:
        hit = self.cassettes(call)
        if hit is not None:
            return hit
        if call.endpoint == "heartbeat":
            return None
        raw = self.transport.get(call)
        back = wiring.call_from_uri(call.source, uri_for(call))
        if back.cache_key != call.cache_key:
            raise RuntimeError(f"cache key does not round-trip for {call.url}")
        self.cassettes.by_key[call.cache_key] = raw
        self.new.append(raw)
        return raw


def interaction(raw: RawResponse) -> dict[str, Any]:
    body = raw.body.decode("utf-8", errors="replace")
    return {
        "request": {"method": "GET", "uri": uri_for(raw.call), "body": None, "headers": {}},
        "response": {
            "status": {"code": raw.status, "message": ""},
            "headers": {"content-type": [raw.content_type or "application/json"]},
            "body": {"string": body},
        },
        "recorded_at": raw.fetched_at.astimezone(UTC).isoformat(timespec="seconds"),
    }


def write(case_id: str, new: list[RawResponse]) -> list[str]:
    by_dir: dict[str, list[RawResponse]] = {}
    for raw in new:
        by_dir.setdefault(DIR_BY_SOURCE[raw.call.source], []).append(raw)
    written = []
    for d, raws in sorted(by_dir.items()):
        path = ADAPTERS / d / f"run_{case_id}.yaml"
        old = yaml.safe_load(path.read_text()) if path.exists() else {"interactions": []}
        old["interactions"].extend(interaction(r) for r in raws)
        old["version"] = 1
        path.write_text(yaml.safe_dump(old, sort_keys=False, allow_unicode=True))
        written.append(f"{path.relative_to(ROOT)} (+{len(raws)})")
    return written


def gaps(bundle: Any) -> list[str]:
    if bundle is None:
        return ["no bundle"]
    return [
        r
        for r in bundle.run.partial_reasons
        if "enrichment unavailable" in r or "no stored response" in r or "no Materials" in r
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="+")
    args = ap.parse_args()
    settings = Settings()
    transport = HttpxTransport(
        settings, client=httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    )
    report: dict[str, Any] = {}
    for case_id in args.cases:
        case = next(c for c in load_cases() if c.id == case_id)
        left: list[str] = []
        for round_no in range(1, MAX_ROUNDS + 1):
            ex = PipelineExecutor(llm="fake", fetch_source="cassettes")
            fill = LiveFill(transport)
            ex._cassettes = fill  # noqa: SLF001 - the executor's fetch slot
            obs = ex.run(case, 1)
            print(f"{case_id} round {round_no}: {len(fill.new)} live responses", flush=True)
            for line in write(case_id, fill.new):
                print(f"  wrote {line}", flush=True)
            replay = PipelineExecutor(llm="fake", fetch_source="cassettes").run(case, 1)
            left = gaps(replay.bundle)
            for err in obs.errors:
                print(f"  run error: {err}", flush=True)
            if not left:
                break
        report[case_id] = {"unavailable_after_cap": left}
        print(f"{case_id}: {len(left)} left after replay", flush=True)
        for r in left:
            print(f"  {r}", flush=True)
    manifest = ADAPTERS / "recording_manifest.json"
    data = json.loads(manifest.read_text())
    runs = data.setdefault("_case_recordings", {})
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    for case_id, entry in report.items():
        runs[case_id] = {**entry, "recorded_at": stamp, "max_rounds": MAX_ROUNDS}
    manifest.write_text(json.dumps(data, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
