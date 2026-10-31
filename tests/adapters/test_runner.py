from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine

from materials_triage.adapters.base import Call, NotFetchedError, RawResponse, Source
from materials_triage.adapters.runner import Runner
from materials_triage.adapters.transport import TransportFailedError
from materials_triage.provenance.store import Store
from tests.conftest import requires_db

pytestmark = requires_db


class CountingTransport:
    def __init__(self, body: bytes = b'{"data": []}', fail: bool = False) -> None:
        self.calls = 0
        self.body = body
        self.fail = fail

    def get(self, call: Call) -> RawResponse:
        self.calls += 1
        if self.fail:
            raise TransportFailedError(call, RuntimeError("connect timeout"))
        return RawResponse(
            call=call,
            status=200,
            body=self.body,
            content_type="application/json",
            fetched_at=datetime.now(UTC),
            source_version="v1",
        )


CALL = Call(
    source=Source.MP,
    endpoint="materials/summary",
    url="https://api.materialsproject.org/materials/summary/",
    params={"formula": "HfO2"},
)


def test_live_mode_fetches_once_then_serves_from_store(app_engine: Engine) -> None:
    t = CountingTransport()
    r = Runner(Store(app_engine), t, mode="live")
    first = r.fetch(CALL)
    second = r.fetch(CALL)
    assert (
        t.calls == 1
        and first.cache_hit is False
        and second.cache_hit is True
        and first.raw_id == second.raw_id
    )


def test_ttl_expiry_triggers_a_new_fetch(app_engine: Engine) -> None:
    t = CountingTransport()
    r = Runner(Store(app_engine), t, mode="live", ttls={Source.MP: timedelta(seconds=0)})
    r.fetch(CALL)
    r.fetch(CALL)
    assert t.calls == 2


def test_replay_mode_never_calls_the_transport(app_engine: Engine) -> None:
    t = CountingTransport()
    store = Store(app_engine)
    Runner(store, CountingTransport(), mode="live").fetch(CALL)
    replay = Runner(store, t, mode="replay")
    assert replay.fetch(CALL).cache_hit is True
    other = Call(
        source=Source.MP, endpoint="materials/summary", url=CALL.url, params={"formula": "ZrO2"}
    )
    with pytest.raises(NotFetchedError):
        replay.fetch(other)
    assert t.calls == 0


def test_version_change_invalidates_mp_cache(app_engine: Engine) -> None:
    t = CountingTransport()
    r = Runner(Store(app_engine), t, mode="live", required_versions={Source.MP: "v1"})
    r.fetch(CALL)
    r.required_versions[Source.MP] = "v2"
    r.fetch(CALL)
    assert t.calls == 2


def test_refresh_appends_a_new_row(app_engine: Engine) -> None:
    store = Store(app_engine)
    Runner(store, CountingTransport(b'{"v": 1}'), mode="live").fetch(CALL)
    fresh = Runner(store, CountingTransport(b'{"v": 2}'), mode="refresh").fetch(CALL)
    assert fresh.raw.body == b'{"v": 2}' and fresh.cache_hit is False
    assert Runner(store, CountingTransport(), mode="replay").fetch(CALL).raw.body == b'{"v": 2}'


def test_transport_failure_becomes_an_availability_event(app_engine: Engine) -> None:
    r = Runner(Store(app_engine), CountingTransport(fail=True), mode="live")
    cod = Call(
        source=Source.COD,
        endpoint="structures",
        url="https://www.crystallography.net/cod/optimade/v1/structures",
        params={},
    )
    assert r.try_fetch(cod) is None
    assert (
        len(r.events) == 1
        and r.events[0].source == Source.COD
        and "connect timeout" in r.events[0].error
    )
