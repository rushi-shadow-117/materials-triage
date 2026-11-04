"""Input limits and the one candidate splitter (Track H).

A typed candidate list is split here and nowhere else: commas, semicolons, and new lines
separate entries; blanks are dropped; a repeat (case-insensitive) keeps its first spelling.
The limits are core configuration (CoreConfig.max_request_chars, max_candidates); the API
refuses over them with a sentence, and the web app reads them to show a counter.
"""

from __future__ import annotations

import re
from typing import Any

from materials_triage.config.schema import CoreConfig

_SEPARATORS = re.compile(r"[,;\n]")


class LimitExceededError(ValueError):
    """An input is over a core limit; the message is the sentence shown to the person."""


def split_candidate_text(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for piece in _SEPARATORS.split(text):
        entry = " ".join(piece.split())
        if not entry:
            continue
        key = entry.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def candidate_entries(settings: dict[str, Any]) -> list[str]:
    """The candidate entries a settings mapping names, before any matching: the typed text
    split, or the list as given."""
    text = settings.get("candidate_text")
    if isinstance(text, str):
        return split_candidate_text(text)
    given = settings.get("candidate_list")
    if isinstance(given, list):
        return [str(c) for c in given]
    return []


def check_request_limits(
    core: CoreConfig, *, request_text: str | None = None, settings: dict[str, Any] | None = None
) -> None:
    """Raise LimitExceededError with a plain sentence when the request text or the candidate list
    is over its core limit."""
    if request_text is not None and len(request_text) > core.max_request_chars:
        raise LimitExceededError(
            f"The request is {len(request_text):,} characters; the limit is "
            f"{core.max_request_chars:,}. Shorten it and try again."
        )
    if settings is not None:
        n = len(candidate_entries(settings))
        if n > core.max_candidates:
            raise LimitExceededError(
                f"{n} candidates were given; the limit is {core.max_candidates}. "
                "Remove some and try again."
            )
