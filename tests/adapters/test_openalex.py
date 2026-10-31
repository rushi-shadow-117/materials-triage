import json
from datetime import UTC, datetime

from materials_triage.adapters import openalex
from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.adapters.transport import HttpxTransport


def test_scope_parameters_and_no_secret_in_plan() -> None:
    search = openalex.plan_search("HfO2 dielectric thin film")
    assert (
        "search.title_and_abstract" in search.params
        and search.params["filter"] == "has_abstract:true"
    )
    assert "api_key" not in search.params
    full = openalex.plan_search("HfO2", scope="fulltext")
    assert "search" in full.params and "search.title_and_abstract" not in full.params
    cnt = openalex.plan_count("HfO2 dielectric thin film")
    assert "filter" not in cnt.params and cnt.params["per-page"] == "1"


def test_abstract_rebuild_is_deterministic() -> None:
    index = {"gate": [2], "HfO2": [0], "a": [1], "oxide": [3, 5], "is": [4]}
    assert openalex.rebuild_abstract(index) == "HfO2 a gate oxide is oxide"
    assert openalex.rebuild_abstract(None) is None and openalex.rebuild_abstract({}) is None


def test_title_and_abstract_search_with_unfiltered_count(
    transport: HttpxTransport, cassette
) -> None:  # type: ignore[no-untyped-def]
    q = "HfO2 dielectric thin film"
    with cassette("openalex", "HfO2_title_abstract"):
        raw_search = transport.get(openalex.plan_search(q))
        raw_count = transport.get(openalex.plan_count(q))
    res = openalex.result(
        raw_search, raw_count, composition="HfO2", query=q, scope="title_and_abstract"
    )
    assert res.matched_total is not None and res.matched_with_abstract is not None
    assert res.matched_total >= res.matched_with_abstract > 0
    assert len(res.hits) == 5
    for h in res.hits:
        assert h.abstract_text and h.abstract_index_sha256 and h.quote_verifiable is True
        assert h.provenance.raw_sha256 == raw_search.sha256
    assert res.hits[0].cost_usd is not None


def test_fulltext_hits_are_marked_unverifiable() -> None:
    body = {
        "meta": {"count": 1, "cost_usd": 0.001},
        "results": [
            {
                "id": "https://openalex.org/W1",
                "abstract_inverted_index": {"x": [0]},
                "primary_location": {},
            }
        ],
    }
    raw = RawResponse(
        call=openalex.plan_search("x", scope="fulltext"),
        status=200,
        body=json.dumps(body).encode(),
        content_type=None,
        fetched_at=datetime.now(UTC),
    )
    res = openalex.result(raw, None, composition="X", query="x", scope="fulltext")
    assert res.hits[0].quote_verifiable is False and res.matched_total is None


def test_missing_abstract_is_none_not_empty_string() -> None:
    body = {
        "meta": {"count": 1},
        "results": [{"id": "https://openalex.org/W2", "primary_location": None}],
    }
    raw = RawResponse(
        call=Call(source=Source.OPENALEX, endpoint="works", url=openalex.BASE, params={}),
        status=200,
        body=json.dumps(body).encode(),
        content_type=None,
        fetched_at=datetime.now(UTC),
    )
    hit = openalex.result(raw, None, composition="X", query="x", scope="title_and_abstract").hits[0]
    assert hit.abstract_text is None and hit.abstract_index_sha256 is None and hit.year is None
