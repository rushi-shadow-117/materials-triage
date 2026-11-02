"""The verifier: runs before any render and strips what the bundle cannot back.

Per rationale slot, in this order, each pass replacing what it accepts with a placeholder so
later passes never see its digits:
  1. template tokens: every argument must resolve against the bundle index;
  2. record ids by shape (mp-, mvc-, JVASP-, OpenAlex W, CID, DOI) must be in the bundle;
  3. oxidation-state tokens such as Cr(VI): the element must occur in the slot's composition;
  4. formula-shaped tokens: parsed with pymatgen only when they carry a digit or parentheses
     (pymatgen reads "CVD" and "ALD" as formulas) and must reduce to a bundle composition;
  5. every remaining digit sequence must equal a display rendering of a number the bundle
     holds for that composition (or a run-level count).
A failure removes the whole sentence, lists it in `removed_fragments`, and logs it. Evidence
quotes must be verbatim substrings of the stored abstract; fulltext-scope hits are never
verified and never rise above computed_only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pymatgen.core.composition import Composition
from pymatgen.core.periodic_table import Element

from materials_triage.records.bundle import (
    Anchor,
    Candidate,
    EvidenceHit,
    EvidenceLabel,
    ProvenanceBundle,
    RationaleSlot,
    VerifierFailure,
    VerifierReport,
)
from materials_triage.render import precision
from materials_triage.render.tokens import TOKEN_RE, BundleIndex, TokenError, resolve
from materials_triage.verify.quotes import check_quote

PLACEHOLDER = "\x00"
ID_RE = re.compile(
    r"https://openalex\.org/W\d+|https://doi\.org/\S+|\b10\.\d{4,}/\S+|"
    r"\bmp-\d+\b|\bmvc-\d+\b|\bJVASP-\d+\b|\bW\d{6,}\b|\bCID:?\s?\d+\b"
)
HCODE_RE = re.compile(r"\bH\d{3}[A-Za-z]{0,2}\b")  # GHS hazard statement codes, e.g. H350i
OXIDATION_RE = re.compile(r"\b([A-Z][a-z]?)\((I|II|III|IV|V|VI|VII|VIII)\)")
FORMULA_RE = re.compile(r"\b(?:\(?[A-Z][a-z]?(?:\d+(?:\.\d+)?)?\)?)+(?:\d+(?:\.\d+)?)?\b")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
ABBREVIATIONS = ("et al.", "e.g.", "i.e.", "vs.", "approx.", "Fig.", "Eq.", "Ref.")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z{(\x00])")
FULLTEXT_NOTE = "fulltext scope; quote not verifiable"
POSITIVE_LABELS = frozenset(
    {
        EvidenceLabel.BULK_SYNTHESIZED,
        EvidenceLabel.THIN_FILM_DEPOSITED,
        EvidenceLabel.DIELECTRIC_CHARACTERIZED,
    }
)


@dataclass
class SlotScope:
    """What one slot may cite: its composition's numbers plus run-level counts."""

    composition: str | None
    allowed_numbers: set[str] = field(default_factory=set)
    elements: set[str] = field(default_factory=set)
    compositions: set[str] = field(default_factory=set)
    h_codes: set[str] = field(default_factory=set)


def split_sentences(text: str) -> list[str]:
    protected = text
    for i, abbr in enumerate(ABBREVIATIONS):
        protected = protected.replace(abbr, f"\x01{i}\x01")
    parts = [p for p in SENTENCE_SPLIT.split(protected) if p.strip()]
    out = []
    for p in parts:
        for i, abbr in enumerate(ABBREVIATIONS):
            p = p.replace(f"\x01{i}\x01", abbr)
        out.append(p)
    return out


# ------------------------------------------------------------------ allowed numbers


def _add(out: set[str], value: float | int | None, unit: str | None) -> None:
    if value is not None:
        out |= precision.renderings(value, unit)


def numbers_for_row(row: Candidate | Anchor) -> set[str]:
    out: set[str] = set()
    if row.score is not None:
        for cs in row.score.criteria:
            if cs.raw_unit is not None:
                _add(out, cs.raw_value, cs.raw_unit)
        _add(out, row.score.total, "score")
    if isinstance(row, Candidate):
        _add(out, row.rank, "rank")
        if row.sensitivity is not None:
            _add(out, row.sensitivity.rank_min, "rank")
            _add(out, row.sensitivity.rank_max, "rank")
    else:
        _add(out, row.would_rank, "rank")
        _add(out, row.out_of, "count")
    g = row.group
    p = g.polymorphs
    for n in (p.total, p.observed_count, p.theoretical_count, p.unknown_count):
        _add(out, n, "count")
    for prow in [p.ground_state, p.lowest_observed, p.scored, *p.top_by_hull]:
        if prow is None:
            continue
        if prow.hull_energy is not None:
            _add(out, prow.hull_energy.value, "eV/atom")
        for v in prow.band_gap.values():
            _add(out, v.value, "eV")
        for v in prow.dielectric.values():
            _add(out, v.value, "1")
        _add(out, prow.spacegroup_number, "count")
    if g.experimental_gaps is not None:
        gaps = g.experimental_gaps
        _add(out, gaps.n, "count")
        for x in (gaps.min, gaps.median, gaps.max):
            _add(out, x, "eV")
        for gap in gaps.values:
            _add(out, gap.value_ev.value, "eV")
    for ref in g.reference_values:
        if ref.value is not None:
            _add(out, ref.value.value, "eV")
        if ref.value_range is not None:
            for x in ref.value_range:
                _add(out, x, "eV")
    if g.hazard is not None:
        _add(out, g.hazard.notifications_total, "count")
        _add(out, g.hazard.notifications_not_classified, "count")
        if (
            g.hazard.notifications_total is not None
            and g.hazard.notifications_not_classified is not None
        ):
            _add(
                out,
                g.hazard.notifications_total - g.hazard.notifications_not_classified,
                "count",
            )
    if g.literature is not None:
        lit = g.literature
        _add(out, lit.matched_total, "count")
        _add(out, lit.matched_with_abstract, "count")
        _add(out, len(lit.hits), "count")
        for hit in lit.hits:
            _add(out, hit.year, "year")
    return out


def run_level_numbers(bundle: ProvenanceBundle) -> set[str]:
    out: set[str] = set()
    _add(out, bundle.criteria.effective_settings.get("top_n"), "count")
    _add(out, len(bundle.ranked()), "count")
    _add(out, len(bundle.candidates), "count")
    _add(out, len(bundle.excluded()), "count")
    for a in bundle.anchors:
        _add(out, a.would_rank, "rank")
        _add(out, a.out_of, "count")
    return out


def _elements(composition: str) -> set[str]:
    try:
        return {e.symbol for e in Composition(composition).elements}
    except (ValueError, KeyError):
        return set()


def _h_codes(row: Candidate | Anchor) -> set[str]:
    return set(row.group.hazard.h_codes) if row.group.hazard is not None else set()


def scope_for(bundle: ProvenanceBundle, index: BundleIndex, slot_id: str) -> SlotScope | None:
    """Slot id grammar: candidate:<comp>:<name> | anchor:<comp>:<name> | summary:<name>."""
    bits = slot_id.split(":")
    compositions = set(index.rows)
    if len(bits) == 3 and bits[0] in ("candidate", "anchor"):
        comp = bits[1]
        if comp not in index.rows:
            return None
        row = index.rows[comp]
        return SlotScope(
            composition=comp,
            allowed_numbers=numbers_for_row(row) | run_level_numbers(bundle),
            elements=_elements(comp),
            compositions=compositions,
            h_codes=_h_codes(row),
        )
    if len(bits) == 2 and bits[0] == "summary":
        allowed = run_level_numbers(bundle)
        elements: set[str] = set()
        codes: set[str] = set()
        for comp, row in index.rows.items():
            allowed |= numbers_for_row(row)
            elements |= _elements(comp)
            codes |= _h_codes(row)
        return SlotScope(None, allowed, elements, compositions, codes)
    return None


# ------------------------------------------------------------------ one slot


@dataclass
class SentenceCheck:
    ok: bool
    kind: str | None = None
    fragment: str | None = None


def _is_element(symbol: str) -> bool:
    try:
        Element(symbol)
    except (ValueError, KeyError):
        return False
    return True


def check_sentence(sentence: str, scope: SlotScope, index: BundleIndex) -> SentenceCheck:
    text = sentence

    # 1. template tokens
    failure: SentenceCheck | None = None

    def _token(m: re.Match[str]) -> str:
        nonlocal failure
        if failure is None:
            try:
                resolve(index, m.group(1), m.group(2))
            except TokenError as e:
                failure = SentenceCheck(False, e.kind, m.group(0))
        return PLACEHOLDER

    text = TOKEN_RE.sub(_token, text)
    if failure is not None:
        return failure

    # 2. record ids
    def _id(m: re.Match[str]) -> str:
        nonlocal failure
        raw = m.group(0)
        candidates = {raw, raw.rstrip(".,;:)"), re.sub(r"^CID:?\s?", "CID:", raw)}
        if failure is None and not (candidates & index.ids):
            failure = SentenceCheck(False, "unknown_record_id", raw)
        return PLACEHOLDER

    text = ID_RE.sub(_id, text)
    if failure is not None:
        return failure

    # 2b. GHS hazard statement codes: only the ones the bundle reports for this composition
    def _hcode(m: re.Match[str]) -> str:
        nonlocal failure
        if failure is None and m.group(0) not in scope.h_codes:
            failure = SentenceCheck(False, "unresolved_number", m.group(0))
        return PLACEHOLDER

    text = HCODE_RE.sub(_hcode, text)
    if failure is not None:
        return failure

    # 3. oxidation-state tokens
    def _oxidation(m: re.Match[str]) -> str:
        nonlocal failure
        if failure is None and m.group(1) not in scope.elements:
            failure = SentenceCheck(False, "formula_not_in_bundle", m.group(0))
        return PLACEHOLDER

    text = OXIDATION_RE.sub(_oxidation, text)
    if failure is not None:
        return failure

    # 4. formula-shaped tokens
    def _formula(m: re.Match[str]) -> str:
        nonlocal failure
        raw = m.group(0)
        if raw in scope.compositions:
            return PLACEHOLDER
        if not any(ch.isdigit() or ch in "()" for ch in raw):
            return raw  # a word or a bare element symbol; carries no digits
        if failure is not None:
            return PLACEHOLDER
        try:
            reduced = Composition(raw).reduced_formula
        except (ValueError, KeyError):
            failure = SentenceCheck(False, "formula_not_in_bundle", raw)
            return PLACEHOLDER
        if reduced not in scope.compositions:
            failure = SentenceCheck(False, "formula_not_in_bundle", raw)
        return PLACEHOLDER

    text = FORMULA_RE.sub(_formula, text)
    if failure is not None:
        return failure

    # 5. remaining digit sequences
    for m in NUMBER_RE.finditer(text):
        if m.group(0) not in scope.allowed_numbers:
            return SentenceCheck(False, "unresolved_number", m.group(0))
    return SentenceCheck(True)


def verify_slot(
    slot: RationaleSlot, scope: SlotScope, index: BundleIndex
) -> tuple[RationaleSlot, list[VerifierFailure]]:
    kept: list[str] = []
    removed: list[str] = []
    failures: list[VerifierFailure] = []
    for sentence in split_sentences(slot.text):
        result = check_sentence(sentence, scope, index)
        if result.ok:
            kept.append(sentence)
        else:
            removed.append(sentence)
            failures.append(
                VerifierFailure(
                    kind=result.kind or "unresolved_number",
                    location=slot.slot,
                    fragment=sentence,
                    action="removed",
                )
            )
    text = " ".join(kept)
    verified = not removed and bool(text.strip())
    return (
        slot.model_copy(
            update={
                "text": text,
                "verified": verified,
                "removed_fragments": [*slot.removed_fragments, *removed],
            }
        ),
        failures,
    )


# ------------------------------------------------------------------ evidence


def _stored_hit_text(bundle: ProvenanceBundle, hit: EvidenceHit) -> tuple[bool, str | None]:
    rows: list[Candidate | Anchor] = [*bundle.candidates, *bundle.anchors]
    for row in rows:
        if row.composition != hit.composition or row.group.literature is None:
            continue
        for lit in row.group.literature.hits:
            if lit.openalex_id == hit.openalex_id:
                return True, lit.abstract_text
    return False, None


def verify_evidence(
    bundle: ProvenanceBundle, hit: EvidenceHit
) -> tuple[EvidenceHit, VerifierFailure | None]:
    found, abstract = _stored_hit_text(bundle, hit)
    if not found:
        return (
            hit.model_copy(update={"verified": False, "verifier_note": "hit not in bundle"}),
            VerifierFailure(
                kind="unknown_record_id",
                location=f"evidence:{hit.openalex_id}",
                fragment=hit.openalex_id,
                action="hit_dropped",
            ),
        )
    if not hit.quote_verifiable:
        label = EvidenceLabel.COMPUTED_ONLY if hit.label in POSITIVE_LABELS else hit.label
        return (
            hit.model_copy(
                update={"verified": False, "verifier_note": FULLTEXT_NOTE, "label": label}
            ),
            None,
        )
    if hit.label in (EvidenceLabel.NO_ABSTRACT, EvidenceLabel.UNCLASSIFIED):
        return hit.model_copy(update={"verified": False, "verifier_note": None}), None
    result = check_quote(hit.supporting_sentence, abstract)
    if result.ok:
        return hit.model_copy(update={"verified": True, "verifier_note": None}), None
    return (
        hit.model_copy(update={"verified": False, "verifier_note": result.note}),
        VerifierFailure(
            kind="quote_mismatch",
            location=f"evidence:{hit.openalex_id}",
            fragment=hit.supporting_sentence or "",
            action="hit_dropped",
        ),
    )


# ------------------------------------------------------------------ whole bundle


def verify(bundle: ProvenanceBundle) -> tuple[ProvenanceBundle, VerifierReport]:
    """Return the bundle with unverifiable text removed and the report describing it."""
    index = BundleIndex.build(bundle)
    failures: list[VerifierFailure] = []
    rationale: dict[str, RationaleSlot] = {}
    for slot_id, slot in bundle.rationale.items():
        scope = scope_for(bundle, index, slot_id)
        if scope is None:
            failures.append(
                VerifierFailure(
                    kind="unknown_record_id", location=slot_id, fragment=slot.text, action="removed"
                )
            )
            continue
        checked, slot_failures = verify_slot(slot, scope, index)
        rationale[slot_id] = checked
        failures.extend(slot_failures)
    evidence: list[EvidenceHit] = []
    for hit in bundle.evidence:
        checked_hit, failure = verify_evidence(bundle, hit)
        evidence.append(checked_hit)
        if failure is not None:
            failures.append(failure)
    report = VerifierReport(
        checked_slots=len(bundle.rationale),
        checked_evidence=len(bundle.evidence),
        failures=failures,
        passed=not failures,
    )
    return bundle.model_copy(
        update={"rationale": rationale, "evidence": evidence, "verifier": report}
    ), report
