import httpx
import pytest

from materials_triage.adapters.base import Auth, Call, Source
from materials_triage.adapters.transport import (
    MAX_ATTEMPTS,
    TIMEOUT,
    HttpxTransport,
    TokenBucket,
    TransportFailedError,
)
from materials_triage.settings import Settings


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        mp_api_key="mp-secret-xyz",
        openalex_api_key="oa-secret-xyz",
        openalex_mailto="a@b.c",
    )


def _transport(handler) -> HttpxTransport:  # type: ignore[no-untyped-def]
    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=TIMEOUT)
    return HttpxTransport(_settings(), client=client, sleep=lambda _s: None)


def test_mp_key_goes_in_header_and_never_in_raw() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": []})

    call = Call(
        source=Source.MP,
        endpoint="materials/summary",
        url="https://api.materialsproject.org/materials/summary/",
        params={"formula": "HfO2"},
        auth=Auth.MP_HEADER,
    )
    raw = _transport(handler).get(call)
    assert seen["headers"]["x-api-key"] == "mp-secret-xyz"
    assert "mp-secret-xyz" not in seen["url"]
    assert "mp-secret-xyz" not in raw.model_dump_json()
    assert raw.sha256 == __import__("hashlib").sha256(raw.body).hexdigest()


def test_openalex_key_goes_in_params_and_never_in_raw() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"results": []})

    call = Call(
        source=Source.OPENALEX,
        endpoint="works",
        url="https://api.openalex.org/works",
        params={"search.title_and_abstract": "HfO2"},
        auth=Auth.OPENALEX_PARAM,
    )
    raw = _transport(handler).get(call)
    assert "api_key=oa-secret-xyz" in seen["url"] and "mailto=a%40b.c" in seen["url"]
    assert "api_key" not in raw.call.params and "mailto" not in raw.call.params
    assert "oa-secret-xyz" not in raw.model_dump_json()


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, content=b"ok")

    raw = _transport(handler).get(
        Call(source=Source.PUBCHEM, endpoint="x", url="https://pubchem.ncbi.nlm.nih.gov/x")
    )
    assert calls["n"] == 3 and raw.status == 200 and raw.body == b"ok"


def test_gives_up_after_max_attempts_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(TransportFailedError) as e:
        _transport(handler).get(
            Call(
                source=Source.COD,
                endpoint="info",
                url="https://www.crystallography.net/cod/optimade/v1/info",
            )
        )
    assert f"after {MAX_ATTEMPTS} attempts" in str(e.value)


def test_non_retryable_status_is_returned_not_raised() -> None:
    raw = _transport(lambda r: httpx.Response(404, content=b"nope")).get(
        Call(source=Source.PUBCHEM, endpoint="x", url="https://pubchem.ncbi.nlm.nih.gov/x")
    )
    assert raw.status == 404


def test_token_bucket_spaces_calls() -> None:
    clock = {"t": 0.0}
    slept: list[float] = []
    bucket = TokenBucket(rate=4.0, clock=lambda: clock["t"])
    bucket.wait(sleep=slept.append)
    bucket.wait(sleep=slept.append)
    assert slept == [pytest.approx(0.25)]


def test_cache_key_ignores_param_order() -> None:
    a = Call(source=Source.MP, endpoint="e", url="https://x/y", params={"a": "1", "b": "2"})
    b = Call(source=Source.MP, endpoint="e", url="https://x/y", params={"b": "2", "a": "1"})
    assert a.cache_key == b.cache_key


def test_explicit_timeouts_are_set() -> None:
    assert TIMEOUT.connect == 15.0 and TIMEOUT.read == 120.0


def test_cache_key_ignores_percent_encoding_differences() -> None:
    a = Call(source=Source.PUBCHEM, endpoint="e", url="https://x/name/hafnium dioxide/cids")
    b = Call(source=Source.PUBCHEM, endpoint="e", url="https://x/name/hafnium%20dioxide/cids")
    assert a.cache_key == b.cache_key
