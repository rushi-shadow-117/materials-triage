"""Display-term mapping from the site glossary, applied only when terminology is general."""

from __future__ import annotations

import re


def apply(text: str, glossary: dict[str, str]) -> str:
    """Replace whole-word occurrences of each glossary term, longest term first, so a term
    that contains another is mapped once. Case-sensitive: the glossary names exact terms."""
    if not glossary:
        return text
    for term in sorted(glossary, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(term)}(?!\w)", glossary[term], text)
    return text
