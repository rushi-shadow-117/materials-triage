"""Does a supporting sentence name the candidate itself? (review F02)

A verbatim quote proves the sentence is in the abstract, not that the abstract is about the
candidate. "B2O3/SiO2 films", "SiO2-P2O5-CaO" and "Li2O-Al2O3" name a mixed system that contains
the candidate. This check passes a sentence only when the candidate's formula appears at least
once as a standalone formula: not part of a longer formula, and not joined to another formula by
an adjacent "-", "/", an en dash, ":" or "x". When the formula does not appear at all, a
standalone synonym from the profile's synonym table counts instead (owner decision, review fix
batch). Text normalization handles the forms OpenAlex abstracts carry: Unicode subscripts,
LaTeX markup ("{\\mathrm{B}}_{2}"), and spaced formulas ("Li 2 O").
"""

from __future__ import annotations

import re
import unicodedata

# Hyphen, en dash, minus sign, non-breaking hyphen, division slash, fraction slash, multiplication
JOINERS = "-/:x\u2010\u2011\u2012\u2013\u2014\u2212\u2215\u2044\u00d7"
_LATEX_CMD = re.compile(r"\\(?:mathrm|text|textrm|mathit|rm)\b")
_LATEX_JUNK = re.compile(r"[{}$_\\]")
# One formula-like token: element chunks with optional counts, possibly spaced ("Li 2 O"), and
# not continued by a lowercase letter (so "Based" or "Films" are words, not formulas).
_ELEMENT = r"[A-Z][a-z]?(?:\s?\d+(?:\.\d+)?)?"
_FORMULA_TOKEN = rf"(?:{_ELEMENT}){{1,8}}(?![a-z])"
_JOIN = rf"\)?\s*[{re.escape(JOINERS)}]\s*\(?"
_LEFT_MIXED = re.compile(rf"(?<![A-Za-z]){_FORMULA_TOKEN}{_JOIN}$")
# A slash names a stack, so one modifier word may sit between it and the next formula
# ("B2O3/passivation SiO2"). Not for a hyphen: "Al2O3-coated Si" is an Al2O3 film.
_RIGHT_MIXED = re.compile(rf"^(?:{_JOIN}|\)?\s*[/\u2215\u2044]\s*[a-z]+\s+){_FORMULA_TOKEN}")


def normalize(text: str) -> str:
    """Plain text for matching: NFKC (which also folds Unicode subscripts), LaTeX markup
    stripped, whitespace collapsed."""
    text = unicodedata.normalize("NFKC", text)
    text = _LATEX_CMD.sub("", text)
    text = _LATEX_JUNK.sub("", text)
    return " ".join(text.split())


def _formula_pattern(composition: str) -> re.Pattern[str]:
    """The composition with optional single spaces between its chunks ("Al 2 O 3")."""
    chunks = re.findall(r"[A-Z][a-z]?|\d+(?:\.\d+)?", composition)
    body = r"\s?".join(re.escape(c) for c in chunks)
    # Not inside a longer formula: no letter or digit immediately before; after it, no digit
    # and no element symbol that would continue the formula.
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![0-9]|[A-Z]|[a-z])")


def _standalone(text: str, start: int, end: int) -> bool:
    return not _LEFT_MIXED.search(text[:start]) and not _RIGHT_MIXED.search(text[end:])


def names_candidate(sentence: str, composition: str, synonyms: list[str] | None = None) -> bool:
    text = normalize(sentence)
    matches = list(_formula_pattern(composition).finditer(text))
    if matches:
        return any(_standalone(text, m.start(), m.end()) for m in matches)
    lowered = text.lower()
    for term in synonyms or []:
        pat = re.compile(rf"(?<![a-z]){re.escape(term.lower())}(?![a-z])")
        for m in pat.finditer(lowered):
            if _standalone(text, m.start(), m.end()):
                return True
    return False
