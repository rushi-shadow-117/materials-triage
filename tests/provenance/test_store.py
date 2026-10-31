import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.provenance.store import MaintenanceStore, Store
from materials_triage.records import Provenance, SourceRecord
from tests.conftest import requires_db

pytestmark = requires_db


def _raw(
    body: bytes = b'{"data": []}',
    params: dict[str, str] | None = None,
    version: str | None = "2026.09.28",
) -> RawResponse:
    call = Call(
        source=Source.MP,
        endpoint="materials/summary",
        url="https://api.materialsproject.org/materials/summary/",
        params=params or {"formula": "ThO2"},
    )
    return RawResponse(
        call=call,
        status=200,
        body=body,
        content_type="application/json",
        fetched_at=datetime.now(UTC),
        source_version=version,
    )


def test_same_body_twice_is_one_raw_row_and_two_fetch_events(app_engine: Engine) -> None:
    store = Store(app_engine)
    id1, new1 = store.put_raw(_raw(), mode="live")
    id2, new2 = store.put_raw(_raw(), mode="live")
    assert id1 == id2 and new1 is True and new2 is False
    with app_engine.connect() as conn:
        assert conn.execute(text("select count(*) from triage.raw_responses")).scalar_one() == 1
        assert conn.execute(text("select count(*) from triage.fetch_events")).scalar_one() == 2


def test_raw_round_trip_preserves_bytes_and_hash(app_engine: Engine) -> None:
    store = Store(app_engine)
    body = b'{"x": 0.0, "note": "exact bytes matter"}'
    raw_id, _ = store.put_raw(_raw(body), mode="live")
    back = store.get_raw(raw_id)
    assert back.body == body and back.sha256 == hashlib.sha256(body).hexdigest()
    assert back.call.params == {"formula": "ThO2"} and back.source_version == "2026.09.28"


def test_lookup_respects_ttl_and_source_version(app_engine: Engine) -> None:
    store = Store(app_engine)
    raw = _raw()
    store.put_raw(raw, mode="live")
    assert store.lookup(raw.call, ttl=timedelta(days=7)) is not None
    assert (
        store.lookup(raw.call, ttl=timedelta(days=7), now=datetime.now(UTC) + timedelta(days=8))
        is None
    )
    assert store.lookup(raw.call, ttl=None, require_source_version="2026.09.28") is not None
    assert store.lookup(raw.call, ttl=None, require_source_version="2027.01.01") is None
    other = Call(
        source=Source.MP, endpoint="materials/summary", url=raw.call.url, params={"formula": "HfO2"}
    )
    assert store.lookup(other, ttl=None) is None


def test_refresh_appends_and_never_overwrites(app_engine: Engine) -> None:
    store = Store(app_engine)
    first = _raw(b'{"v": 1}')
    second = _raw(b'{"v": 2}')
    id1, _ = store.put_raw(first, mode="live")
    id2, _ = store.put_raw(second, mode="refresh")
    assert id1 != id2
    found = store.lookup(first.call, ttl=None)
    assert found is not None and found[1].body == b'{"v": 2}'
    assert store.get_raw(id1).body == b'{"v": 1}'


def test_app_role_cannot_update_delete_or_run_ddl(app_engine: Engine) -> None:
    store = Store(app_engine)
    store.put_raw(_raw(), mode="live")
    for stmt in (
        "update triage.raw_responses set status = 1",
        "delete from triage.raw_responses",
        "create table triage.oops (x int)",
        "drop table triage.records",
    ):
        with pytest.raises(ProgrammingError), app_engine.begin() as conn:
            conn.execute(text(stmt))


def test_maint_role_deletes_and_logs(app_engine: Engine, maint_engine: Engine) -> None:
    store = Store(app_engine)
    old = _raw(b'{"old": true}')
    store.put_raw(old, mode="live")
    deleted = MaintenanceStore(maint_engine).delete_fetch_events_before(
        datetime.now(UTC) + timedelta(seconds=1), reason="test"
    )
    assert deleted == 1
    with app_engine.connect() as conn:
        row = conn.execute(text("select action, details from triage.maintenance_log")).one()
    assert row.action == "delete_fetch_events_before" and row.details["deleted"] == 1
    with pytest.raises(ProgrammingError), maint_engine.begin() as conn:
        conn.execute(
            text(
                conn.execute(
                    text(
                        "insert into triage.raw_responses "
                        "(source, endpoint, url, params, cache_key, status, body, sha256, "
                        "first_fetched_at) "
                        "values ('x','y','z','{}','k',200,'\\x00','s', now())"
                    )
                )
            )
        )


def test_records_point_at_their_raw_row(app_engine: Engine) -> None:
    store = Store(app_engine)
    raw = _raw()
    raw_id, _ = store.put_raw(raw, mode="live")
    prov = Provenance(
        source="materials_project",
        source_record_id="mp-643",
        raw_response_id=raw_id,
        raw_sha256=raw.sha256,
        fetched_at=raw.fetched_at,
    )
    rec = SourceRecord(
        kind="polymorph",
        source_record_id="mp-643",
        composition="ThO2",
        payload={"composition": "ThO2", "hull": 0.0},
        provenance=prov,
    )
    ids = store.put_records([rec], raw_id=raw_id)
    assert len(ids) == 1
    rows = store.records_for(source="materials_project", kind="polymorph", composition="ThO2")
    assert rows[0]["payload"]["hull"] == 0.0
    assert store.get_raw(rows[0]["raw_response_id"]).sha256 == prov.raw_sha256
