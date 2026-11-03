"""Build the pieces a CLI command needs from settings and config: config layers, the fetch
function (store-backed Runner, or recorded cassettes with no database), the LLM client, the
scorer, the classifier cache, and the run store."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from uuid import UUID

import httpx
import yaml

from materials_triage.adapters.base import Auth, Call, RawResponse, Source
from materials_triage.adapters.runner import Runner
from materials_triage.adapters.transport import TIMEOUT, USER_AGENT, HttpxTransport
from materials_triage.agent import pipeline, scoring_port
from materials_triage.agent.classifier import ClassifierCache
from materials_triage.agent.llm import LLMClient, make_client
from materials_triage.config import schema as cs
from materials_triage.provenance.store import Store, make_engine
from materials_triage.records.bundle import FetchMode
from materials_triage.settings import Settings

from .runs import RunStore

FetchSource = Literal["store", "cassettes"]
ROOT = Path(__file__).resolve().parents[3]
ADAPTER_CASSETTES = ROOT / "fixtures" / "adapters"


@dataclass
class Layers:
    core: cs.CoreConfig
    site: cs.SiteProfile
    profile: cs.ScoringProfile
    hazard_policy: dict[str, Any]
    notes: list[str]


def load_layers(profile_name: str) -> Layers:
    paths = cs.default_paths()
    profile_path = cs.CONFIG_DIR / "scoring_profiles" / f"{profile_name}.yaml"
    if not profile_path.exists():
        raise FileNotFoundError(f"no scoring profile {profile_name!r} under {profile_path.parent}")
    profile, notes = cs.scoring_profile_from_yaml(profile_path)
    site = cs.site_profile_from_yaml(paths["site_profile"])
    hazard = cs.load_yaml(paths["hazard_policy"])
    return Layers(cs.CoreConfig(), site, profile, hazard, notes)


class NoNetwork:
    def get(self, call: Call) -> RawResponse:
        raise RuntimeError(f"network call attempted in replay: {call.url}")


SOURCE_BY_DIR = {
    "mp": Source.MP,
    "openalex": Source.OPENALEX,
    "pubchem": Source.PUBCHEM,
    "oqmd": Source.OQMD,
    "cod": Source.COD,
}
AUTH_BY_SOURCE = {Source.MP: Auth.MP_HEADER, Source.OPENALEX: Auth.OPENALEX_PARAM}


def call_from_uri(source: Source, uri: str) -> Call:
    """The same mapping scripts/seed_store_from_cassettes.py uses, so cache keys agree."""
    parts = urlsplit(uri)
    params = {
        k: v
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in {"api_key", "mailto"}
    }
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    endpoint = parts.path.strip("/").replace("rest/", "").replace("optimade/v1/", "")
    return Call(
        source=source,
        endpoint=endpoint,
        url=url,
        params=params,
        auth=AUTH_BY_SOURCE.get(source, Auth.NONE),
    )


def iter_cassette_raws(root: Path) -> Iterator[tuple[Path, RawResponse]]:
    """Every recorded interaction under fixtures/adapters/<source>/*.yaml as a RawResponse."""
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


class CassetteFetch:
    """Recorded cassettes served by cache key; no database, no network. A dev and CI path."""

    def __init__(self, root: Path = ADAPTER_CASSETTES) -> None:
        self.by_key: dict[str, RawResponse] = {}
        for _path, raw in iter_cassette_raws(root):
            self.by_key.setdefault(raw.call.cache_key, raw)

    def __call__(self, call: Call) -> RawResponse | None:
        return self.by_key.get(call.cache_key)


def make_fetch(
    settings: Settings, source: FetchSource, *, run_id: UUID | None = None
) -> tuple[pipeline.Fetch, FetchMode]:
    if source == "cassettes":
        return CassetteFetch(), FetchMode.REPLAY
    store = Store(make_engine(settings.database_url))
    mode = settings.fetch_mode
    transport: Any
    if mode == "replay":
        transport = NoNetwork()
    else:
        transport = HttpxTransport(
            settings,
            client=httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}),
            sleep=time.sleep,
        )
    runner = Runner(store, transport, mode=mode, run_id=run_id)

    def fetch(call: Call) -> RawResponse | None:
        fetched = runner.try_fetch(call)
        return None if fetched is None else fetched.raw

    return fetch, FetchMode(mode)


def make_llm(settings: Settings, *, no_llm: bool) -> LLMClient | None:
    return None if no_llm else make_client(settings)


def make_scorer() -> scoring_port.Scorer:
    return scoring_port.default_scorer()


def make_cache(settings: Settings) -> ClassifierCache:
    return ClassifierCache(settings.data_cache_dir / "classifier")


def make_run_store(settings: Settings) -> RunStore:
    return RunStore(settings.data_cache_dir / "runs")
