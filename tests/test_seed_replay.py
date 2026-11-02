"""Plan verification 2: seed the store from cassettes, then replay with no network at all."""

from pathlib import Path

import pytest
from scripts.seed_store_from_cassettes import iter_raw
from sqlalchemy import Engine

from materials_triage.adapters import mp, openalex, pubchem
from materials_triage.adapters.base import Call, RawResponse
from materials_triage.adapters.runner import Runner
from materials_triage.provenance.store import Store
from tests.conftest import requires_db

pytestmark = requires_db
ADAPTERS = Path(__file__).resolve().parents[1] / "fixtures" / "adapters"


class NoNetwork:
    def get(self, call: Call) -> RawResponse:
        raise AssertionError(f"network call attempted in replay: {call.url}")


def test_seed_then_replay_serves_every_recorded_call(app_engine: Engine) -> None:
    store = Store(app_engine)
    seeded = [raw for _, raw in iter_raw(ADAPTERS)]
    assert len(seeded) > 10
    for raw in seeded:
        store.put_raw(raw, mode="seed")
    runner = Runner(store, NoNetwork(), mode="replay")
    tho2 = runner.fetch(mp.plan_summary_by_formula("ThO2"))
    assert tho2.cache_hit is True
    assert {p.ids.mp for p in mp.assemble(mp.summary_records(tho2.raw)).polymorphs} == {
        "mp-643",
        "mp-1102569",
    }
    lit = runner.fetch(openalex.plan_search("HfO2 dielectric thin film"))
    assert lit.cache_hit is True and openalex.count(lit.raw)
    haz = runner.fetch(pubchem.plan_cids_by_name("hafnium dioxide"))
    assert pubchem.cids(haz.raw) == [292779]
    with pytest.raises(Exception, match="no stored response"):
        runner.fetch(mp.plan_summary_by_formula("NeverRecorded2"))


def test_every_recorded_interaction_replays_from_the_store(app_engine: Engine) -> None:
    """Plan verification 2 at full scale: after seeding, every recorded call is served with the
    network disabled. Non-200 recordings are seeded too and replay with their status."""
    store = Store(app_engine)
    raws = [raw for _, raw in iter_raw(ADAPTERS)]
    for raw in raws:
        store.put_raw(raw, mode="seed")
    runner = Runner(store, NoNetwork(), mode="replay")
    served = 0
    for raw in raws:
        fetched = runner.fetch(raw.call)
        assert fetched.cache_hit is True and fetched.raw.sha256 == raw.sha256
        served += 1
    assert served == len(raws) > 300
