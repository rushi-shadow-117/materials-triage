"""Build the pieces a CLI command needs from settings and config: config layers, the fetch
function (store-backed Runner, or recorded cassettes with no database), the LLM client, the
scorer, the classifier cache, and the run store."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from uuid import UUID

import httpx
import yaml
from sqlalchemy import create_engine, text

from materials_triage.adapters.base import Auth, Call, RawResponse, Source
from materials_triage.adapters.runner import Runner
from materials_triage.adapters.transport import TIMEOUT, USER_AGENT, HttpxTransport
from materials_triage.agent import llm_status, pipeline, scoring_port
from materials_triage.agent.classifier import ClassifierCache
from materials_triage.agent.llm import LLMClient, make_client
from materials_triage.config import schema as cs
from materials_triage.provenance.store import Store, make_engine
from materials_triage.records.bundle import FetchMode
from materials_triage.settings import MissingSettingError, Settings

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
        cassette = yaml.load(path.read_text(), Loader=_YAML_LOADER)  # noqa: S506 - trusted fixtures
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


_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)  # the C loader is much faster


@functools.lru_cache(maxsize=1)
def cassette_fetch() -> CassetteFetch:
    """The process-wide cassette index: built once (about 20 MB of YAML), reused by every
    run, the health page, and the API."""
    return CassetteFetch()


class CassetteFetch:
    """Recorded cassettes served by cache key; no database, no network. A dev and CI path."""

    def __init__(self, root: Path = ADAPTER_CASSETTES) -> None:
        self.by_key: dict[str, RawResponse] = {}
        for _path, raw in iter_cassette_raws(root):
            self.by_key.setdefault(raw.call.cache_key, raw)

    def __call__(self, call: Call) -> RawResponse | None:
        return self.by_key.get(call.cache_key)


def postgres_reachable(url: str, *, timeout_s: int = 2) -> bool:
    """One short connect attempt; any failure means no usable store."""
    try:
        engine = create_engine(url, connect_args={"connect_timeout": timeout_s}, future=True)
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        engine.dispose()
        return True
    except Exception:  # noqa: BLE001 - unreachable, refused, auth: all mean "use cassettes"
        return False


def resolve_fetch_source(
    settings: Settings,
    requested: str,
    *,
    reachable: Callable[[str], bool] = postgres_reachable,
) -> tuple[FetchSource, str]:
    """`auto` (the CLI and API default): the recorded cassettes unless FETCH_MODE is set; with
    FETCH_MODE set, the store when Postgres answers, else the cassettes. Returns the source
    and the line logged to stderr and the decision log."""
    if requested == "store":
        return "store", "fetch: store (requested)"
    if requested == "cassettes":
        return "cassettes", "fetch: cassettes (requested)"
    if requested != "auto":
        raise ValueError("--fetch must be auto, store, or cassettes")
    if settings.fetch_mode is None:
        return "cassettes", "fetch: cassettes (FETCH_MODE not set: recorded data, no network)"
    parts = urlsplit(settings.database_url)
    where = f"{parts.hostname}:{parts.port}"
    if reachable(settings.database_url):
        return "store", f"fetch: store (Postgres reachable at {where})"
    return "cassettes", f"fetch: cassettes (Postgres not reachable at {where})"


def make_fetch(
    settings: Settings, source: FetchSource, *, run_id: UUID | None = None
) -> tuple[pipeline.Fetch, FetchMode]:
    if source == "cassettes":
        return cassette_fetch(), FetchMode.REPLAY
    store = Store(make_engine(settings.database_url))
    mode = settings.fetch_mode or "live"  # --fetch store with FETCH_MODE unset: live
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


def initial_llm_status(settings: Settings) -> None:
    """Set the process's model status from configuration alone (no request is made)."""
    llm_status.reset()
    if settings.llm_provider == "none":
        llm_status.set_status("none")
    elif settings.llm_provider == "anthropic" and settings.anthropic_api_key is None:
        llm_status.set_status("missing_key", "ANTHROPIC_API_KEY")


def make_llm(settings: Settings, *, no_llm: bool) -> LLMClient | None:
    """The configured client wrapped so a rejected key or exhausted credit falls back to no
    model, or None when no model is configured, the key is missing, or it already failed."""
    if no_llm or settings.llm_provider == "none" or not llm_status.available():
        return None
    try:
        client = make_client(settings)
    except MissingSettingError as e:
        llm_status.set_status("missing_key", e.variable)
        return None
    return None if client is None else llm_status.GuardedClient(client)


def make_scorer() -> scoring_port.Scorer:
    return scoring_port.default_scorer()


def make_cache(settings: Settings) -> ClassifierCache:
    return ClassifierCache(settings.data_cache_dir / "classifier")


def make_run_store(settings: Settings) -> RunStore:
    return RunStore(settings.data_cache_dir / "runs")
