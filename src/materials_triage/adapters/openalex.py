"""OpenAlex works search. Default scope is title and abstract; fulltext is an option whose
hits cannot be verified by the quote check. Each search also records the unfiltered match
count so a row can say "N matched, M had abstracts". Abstracts arrive as inverted indexes."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from materials_triage.adapters.base import Auth, Call, RawResponse, Source
from materials_triage.adapters.common import int_or_none, provenance
from materials_triage.records import LiteratureHit, LiteratureSearchResult

BASE = "https://api.openalex.org/works"
SELECT = "id,doi,title,publication_year,abstract_inverted_index,primary_location"
SCOPES = {"title_and_abstract": "search.title_and_abstract", "fulltext": "search"}


def plan_search(query: str, *, scope: str = "title_and_abstract", per_page: int = 5) -> Call:
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope}")
    return Call(
        source=Source.OPENALEX,
        endpoint="works",
        url=BASE,
        params={
            SCOPES[scope]: query,
            "filter": "has_abstract:true",
            "per-page": str(per_page),
            "select": SELECT,
        },
        auth=Auth.OPENALEX_PARAM,
    )


def plan_count(query: str, *, scope: str = "title_and_abstract") -> Call:
    """Same query without the abstract filter; only meta.count is used."""
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope}")
    return Call(
        source=Source.OPENALEX,
        endpoint="works_count",
        url=BASE,
        params={SCOPES[scope]: query, "per-page": "1", "select": "id"},
        auth=Auth.OPENALEX_PARAM,
    )


def rebuild_abstract(index: dict[str, list[int]] | None) -> str | None:
    """Deterministic: words sorted by position, joined with single spaces."""
    if not index:
        return None
    positions = sorted((pos, word) for word, poss in index.items() for pos in poss)
    return " ".join(word for _, word in positions)


def _body(raw: RawResponse) -> dict[str, Any]:
    body = json.loads(raw.body)
    if not isinstance(body, dict) or "meta" not in body:
        raise ValueError("unexpected OpenAlex body")
    return body


def count(raw: RawResponse) -> int | None:
    return int_or_none(_body(raw)["meta"].get("count"))


def result(
    raw_search: RawResponse,
    raw_count: RawResponse | None,
    *,
    composition: str,
    query: str,
    scope: str,
) -> LiteratureSearchResult:
    body = _body(raw_search)
    cost = body["meta"].get("cost_usd")
    hits = []
    for w in body.get("results", []):
        index = w.get("abstract_inverted_index")
        text = rebuild_abstract(index)
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        oa_id = str(w["id"])
        hits.append(
            LiteratureHit(
                openalex_id=oa_id,
                doi=w.get("doi"),
                title=w.get("title"),
                year=int_or_none(w.get("publication_year")),
                abstract_text=text,
                abstract_index_sha256=hashlib.sha256(
                    json.dumps(index, sort_keys=True).encode()
                ).hexdigest()
                if index
                else None,
                is_oa=loc.get("is_oa"),
                license=loc.get("license"),
                source_name=src.get("display_name"),
                landing_page_url=loc.get("landing_page_url"),
                query=query,
                scope=scope,
                quote_verifiable=(scope == "title_and_abstract"),
                cost_usd=float(cost) if cost is not None else None,
                provenance=provenance(
                    raw_search, source_record_id=oa_id, url=oa_id, license=loc.get("license")
                ),
            )
        )
    return LiteratureSearchResult(
        composition=composition,
        query=query,
        scope=scope,
        matched_total=count(raw_count) if raw_count else None,
        matched_with_abstract=int_or_none(body["meta"].get("count")),
        hits=hits,
    )
