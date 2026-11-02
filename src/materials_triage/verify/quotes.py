"""The verbatim quote check, in one place so the classify handler and the verifier agree.

The stored abstract text is already the deterministic rebuild from the inverted index
(adapters.openalex.rebuild_abstract). The check is an exact substring test with no Unicode
normalization: a quote the model "tidied" is a mismatch by definition.
"""

from __future__ import annotations

from dataclasses import dataclass

NOT_FOUND = "quote not found verbatim in stored abstract"
EMPTY = "empty quote"
NO_ABSTRACT = "no stored abstract to check against"


@dataclass(frozen=True)
class QuoteCheck:
    ok: bool
    note: str | None = None


def check_quote(sentence: str | None, abstract_text: str | None) -> QuoteCheck:
    if sentence is None or not sentence.strip():
        return QuoteCheck(False, EMPTY)
    if abstract_text is None:
        return QuoteCheck(False, NO_ABSTRACT)
    if sentence in abstract_text:
        return QuoteCheck(True, None)
    return QuoteCheck(False, NOT_FOUND)
