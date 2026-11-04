"""Egress allowlist, enforced in code before any request is sent.

Data sources: `CoreConfig.allowed_hosts`. The LLM: only the configured provider's endpoint.
`HttpxTransport.get` checks every call; the LLM clients' HTTP clients run `request_hook` on
every request. A refused host raises `EgressRefusedError` and nothing is sent.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urlsplit

from materials_triage.config.schema import CoreConfig
from materials_triage.settings import Settings

ANTHROPIC_DEFAULT = "https://api.anthropic.com"


class EgressRefusedError(RuntimeError):
    def __init__(self, url: str, allowed: Iterable[str]) -> None:
        super().__init__(f"egress refused: {host_of(url)!r} is not in {sorted(allowed)}")
        self.url = url


def host_of(url: Any) -> str | None:
    host = urlsplit(str(url)).hostname
    return host.lower() if host else None


def check(url: Any, allowed: Iterable[str]) -> None:
    hosts = {h.lower() for h in allowed}
    if host_of(url) not in hosts:
        raise EgressRefusedError(str(url), hosts)


def request_hook(allowed: Iterable[str]) -> Callable[[Any], None]:
    """An httpx (or httpx2) request event hook. `allowed` may be a set filled in after the
    client is built (the hook reads it at request time)."""

    def hook(request: Any) -> None:
        check(request.url, allowed)

    return hook


def llm_endpoint_host(settings: Settings) -> str | None:
    """The host the configured LLM provider sends to; None for provider none."""
    provider = settings.llm_provider
    if provider == "anthropic":
        return host_of(os.environ.get("ANTHROPIC_BASE_URL") or ANTHROPIC_DEFAULT)
    if provider == "bedrock":
        return (
            None if settings.aws_region is None else f"bedrock-mantle.{settings.aws_region}.api.aws"
        )
    if provider == "openai_compatible":
        return None if settings.llm_base_url is None else host_of(settings.llm_base_url)
    return None


def allowed_hosts(
    settings: Settings | None = None, core: CoreConfig | None = None
) -> frozenset[str]:
    """CoreConfig.allowed_hosts plus the configured LLM endpoint."""
    hosts = {h.lower() for h in (core or CoreConfig()).allowed_hosts}
    if settings is not None:
        llm = llm_endpoint_host(settings)
        if llm:
            hosts.add(llm)
    return frozenset(hosts)
