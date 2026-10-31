"""httpx transport with explicit timeouts, per-source rate limits, retries, secret injection."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from materials_triage.adapters.base import Auth, Call, RawResponse, Source
from materials_triage.settings import Settings

# Phase 0 lesson: a hung connection to COD was never cut by the default timeout.
TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=15.0)

# Requests per second. PubChem documents a limit of 5/s; stay under it.
RATE_LIMITS: dict[Source, float] = {Source.PUBCHEM: 4.0}
DEFAULT_RATE = 10.0

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
USER_AGENT = "materials-triage/0.0.1 (+https://github.com/rushi-shadow-117/materials-triage)"


class TokenBucket:
    """Simple per-source limiter: at most `rate` calls per second, burst of one."""

    def __init__(self, rate: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._interval = 1.0 / rate
        self._clock = clock
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def wait(self, sleep: Callable[[float], None] = time.sleep) -> None:
        with self._lock:
            now = self._clock()
            delay = self._next_allowed - now
            if delay > 0:
                sleep(delay)
                now = self._clock()
            self._next_allowed = max(now, self._next_allowed) + self._interval


class HttpxTransport:
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        self._sleep = sleep
        self._buckets = {s: TokenBucket(RATE_LIMITS.get(s, DEFAULT_RATE)) for s in Source}

    def get(self, call: Call) -> RawResponse:
        headers, params = self._authenticate(call)
        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._buckets[call.source].wait(self._sleep)
            try:
                # Explicit on every request: a client built without TIMEOUT cannot bypass it.
                response = self._client.get(
                    call.url, params=params, headers=headers, timeout=TIMEOUT
                )
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = e
                self._backoff(attempt)
                continue
            if response.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                self._backoff(attempt, response.headers.get("Retry-After"))
                continue
            return RawResponse(
                call=call,
                status=response.status_code,
                body=response.content,
                content_type=response.headers.get("content-type"),
                fetched_at=datetime.now(UTC),
            )
        raise TransportFailedError(call, last_error)

    def _authenticate(self, call: Call) -> tuple[dict[str, str], dict[str, str]]:
        headers: dict[str, str] = {}
        params = dict(call.params)
        if call.auth is Auth.MP_HEADER:
            headers["X-API-KEY"] = self._settings.require("mp_api_key")
        elif call.auth is Auth.OPENALEX_PARAM:
            params["api_key"] = self._settings.require("openalex_api_key")
            if self._settings.openalex_mailto:
                params["mailto"] = self._settings.openalex_mailto
        return headers, params

    def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        if retry_after and retry_after.isdigit():
            self._sleep(float(retry_after))
            return
        self._sleep(min(30.0, (2.0**attempt) + random.uniform(0, 0.5)))  # noqa: S311


class TransportFailedError(RuntimeError):
    def __init__(self, call: Call, cause: Exception | None) -> None:
        super().__init__(
            f"{call.source} {call.endpoint} failed after {MAX_ATTEMPTS} attempts: {cause!r}"
        )
        self.call = call
        self.cause = cause
