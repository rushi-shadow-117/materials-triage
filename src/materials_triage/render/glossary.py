"""Display-term mapping from the site glossary, applied only when terminology is general."""

from __future__ import annotations

import re


def apply(text: str, glossary: dict[str, str]) -> str:
    """Replace whole-word occurrences of each glossary term, longest term first, so a term
    that contains another is mapped once. A term matches as written and with its first letter
    capitalized (a heading or a sentence start); the replacement follows the same case."""
    if not glossary:
        return text
    for term in sorted(glossary, key=len, reverse=True):
        plain = glossary[term]
        forms = {term: plain, term[:1].upper() + term[1:]: plain[:1].upper() + plain[1:]}
        for found, replacement in forms.items():
            text = re.sub(rf"(?<!\w){re.escape(found)}(?!\w)", replacement, text)
    return text
