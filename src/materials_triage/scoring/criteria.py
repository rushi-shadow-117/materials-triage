"""Per-criterion normalization to 0..1. Pure functions; each docstring states the function.

A criterion returns a `CriterionResult`: the normalized value (None when the input is
missing, with the reason), the raw value with its unit and provenance, an optional hard
exclusion, and the flags, caveats, and notes the row should carry. Missing is never zero.
Band gap and hazard have their own modules; this one holds the rest and the shared types.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pymatgen.core.composition import Composition

from materials_triage.config.schema import SimplicitySettings
from materials_triage.records import (
    LiteratureSearchResult,
    MissingReason,
    Polymorph,
    Provenance,
    Value,
)
from materials_triage.records.bundle import (
    Caveat,
    CaveatId,
    CriterionScore,
    EvidenceHit,
    EvidenceLabel,
    Exclusion,
    ExclusionRule,
    Flag,
)


@dataclass(frozen=True)
class CriterionResult:
    normalized: float | None
    raw_value: float | None = None
    raw_unit: str | None = None
    source: str | None = None
    provenance: Provenance | None = None
    used_record_ids: tuple[str, ...] = ()  # every record whose value entered raw_value
    missing_reason: str | None = None
    exclusion: Exclusion | None = None
    flags: tuple[Flag, ...] = ()
    caveats: tuple[Caveat, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def missing(self) -> bool:
        return self.normalized is None

    def to_score(self, criterion: str, weight: float) -> CriterionScore:
        contribution = 0.0 if self.normalized is None else self.normalized * weight
        reason = self.missing_reason
        if self.missing and reason is None and self.exclusion is not None:
            reason = f"excluded by {self.exclusion.rule.value}"
        return CriterionScore(
            criterion=criterion,
            raw_value=self.raw_value,
            raw_unit=self.raw_unit,
            source=self.source,
            normalized=self.normalized,
            weight=weight,
            contribution=contribution,
            missing=self.missing,
            missing_reason=reason if self.missing else None,
            provenance=self.provenance,
            used_record_ids=list(self.used_record_ids),
            notes=list(self.notes),
        )


def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def missing(
    reason: str, *, source: str | None = None, notes: tuple[str, ...] = ()
) -> CriterionResult:
    return CriterionResult(normalized=None, source=source, missing_reason=reason, notes=notes)


# ----------------------------------------------------------------------------- stability


def stability(
    hull: Value[float] | None,
    *,
    cutoff_mev: float,
    near_cutoff_band_mev: float | None,
    source_ref: str,
) -> CriterionResult:
    """Linear ramp on the energy above the mixed hull, in meV/atom: 1.0 at 0, 0.0 at the
    cutoff, excluded above it (`stability.cutoff`). Within `near_cutoff_band_mev` of the cutoff
    on either side the row is flagged `near_cutoff`. An exact 0.0 scores 1.0; a missing hull
    is missing, never 0."""
    if hull is None or hull.value is None:
        reason = str(hull.missing_reason) if hull is not None and hull.missing_reason else "absent"
        return missing(reason, source=None if hull is None else hull.method)
    mev = hull.value * 1000.0
    flags: tuple[Flag, ...] = ()
    if near_cutoff_band_mev is not None and abs(mev - cutoff_mev) <= near_cutoff_band_mev:
        flags = (Flag.NEAR_CUTOFF,)
    if mev > cutoff_mev:
        return CriterionResult(
            normalized=None,
            raw_value=hull.value,
            raw_unit=hull.unit,
            source=hull.method,
            provenance=hull.provenance,
            missing_reason=None,
            exclusion=Exclusion(
                rule=ExclusionRule.STABILITY_CUTOFF,
                detail=(
                    f"{mev:.1f} meV/atom above the hull exceeds the {cutoff_mev:g} meV/atom cutoff"
                ),
                source_ref=source_ref,
            ),
            flags=flags,
        )
    return CriterionResult(
        # A cutoff of 0 (on the hull only) leaves no ramp: every row that is not excluded scores 1.
        normalized=1.0 if cutoff_mev <= 0 else clamp01(1.0 - mev / cutoff_mev),
        raw_value=hull.value,
        raw_unit=hull.unit,
        source=hull.method,
        provenance=hull.provenance,
        flags=flags,
        caveats=(Caveat(id=CaveatId.STABILITY_CUTOFF_HULL_MISMATCH, source_ref=source_ref),),
    )


# ----------------------------------------------------------------------------- structure


def structure(
    scored: Polymorph | None, *, exclude: list[int], source_ref: str
) -> tuple[Value[int] | None, str | None, Exclusion | None]:
    """The scored polymorph's structural dimensionality (Larsen 2019, computed in
    records/structure.py) and, when it is in the profile's `exclude` list, the exclusion
    `structure.molecular`. A missing dimensionality never excludes; the note says why."""
    if scored is None:
        return None, "no scored polymorph", None
    dim = scored.dimensionality
    if dim is None:
        return None, "structure not fetched (summary-level row)", None
    if dim.value is None:
        return dim, f"dimensionality not computed ({dim.missing_reason})", None
    if dim.value in exclude:
        return (
            dim,
            None,
            Exclusion(
                rule=ExclusionRule.STRUCTURE_MOLECULAR,
                detail=(
                    # the record id last: the PI view swaps it for "a source record (see the
                    # audit view)", which beside the citation read as two parentheticals
                    f"structural dimensionality {dim.value} (Larsen 2019, CrystalNN bonds) on "
                    f"{scored.ids.mp}: isolated molecules, not an extended solid"
                ),
                source_ref=source_ref,
            ),
        )
    return dim, None, None


# ----------------------------------------------------------------------------- simplicity


def elements_of(composition: str) -> list[str]:
    return sorted(e.symbol for e in Composition(composition).elements)


ANION_STATE = {"strict_oxide": ("O", -2.0), "strict_nitride": ("N", -3.0)}
ANION_REASON = "polyatomic or non-oxide/nitride anion (e.g. peroxide, azide)"


def meets_anion_policy(composition: str, policy: str) -> bool:
    """Owner decision 2026-11-04: strict_oxide needs every O at -2 and strict_nitride every N
    at -3 in some pymatgen oxidation-state guess for the composition, with no other element
    negative in that guess. No such guess (none at all, as for peroxides, or N at -1/3, as for
    azides) fails the policy."""
    element, state = ANION_STATE[policy]
    for guess in Composition(composition).oxi_state_guesses():
        if element not in guess or abs(guess[element] - state) > 1e-6:
            continue
        if all(v >= 0 for el, v in guess.items() if el != element):
            return True
    return False


def simplicity(
    composition: str, settings: SimplicitySettings, *, source_ref: str
) -> CriterionResult:
    """Element count against `max_elements` (hard), anion policy (hard), then a penalty for
    more than two elements. Normalized: 1.0 for binaries; for n > 2, `1 - ternary_penalty_size`
    when entered, else `(max_elements + 1 - n) / (max_elements - 1)` (0.5 for a ternary at
    max 3); 1.0 for every allowed count when the penalty is off."""
    els = elements_of(composition)
    n = len(els)
    if n > settings.max_elements:
        return CriterionResult(
            normalized=None,
            raw_value=float(n),
            raw_unit="elements",
            source="composition",
            exclusion=Exclusion(
                rule=ExclusionRule.SIMPLICITY_MAX_ELEMENTS,
                detail=f"{n} elements exceeds max_elements {settings.max_elements}",
                source_ref=source_ref,
            ),
        )
    flags: tuple[Flag, ...] = ()
    caveats: tuple[Caveat, ...] = ()
    notes: tuple[str, ...] = ()
    if settings.anion_policy != "any" and not meets_anion_policy(
        composition, settings.anion_policy
    ):
        element, state = ANION_STATE[settings.anion_policy]
        return CriterionResult(
            normalized=None,
            raw_value=float(n),
            raw_unit="elements",
            source="composition",
            exclusion=Exclusion(
                rule=ExclusionRule.SIMPLICITY_ANION_POLICY,
                detail=(
                    f"{ANION_REASON}: no oxidation-state assignment puts every {element} at "
                    f"{state:g} ({settings.anion_policy})"
                ),
                source_ref=source_ref,
            ),
        )
    if n <= 2 or not settings.ternary_penalty:
        score = 1.0
    elif settings.ternary_penalty_size is not None:
        score = clamp01(1.0 - settings.ternary_penalty_size)
    else:
        score = clamp01((settings.max_elements + 1 - n) / (settings.max_elements - 1))
    return CriterionResult(
        normalized=score,
        raw_value=float(n),
        raw_unit="elements",
        source="composition",
        flags=flags,
        caveats=caveats,
        notes=notes,
    )


# ----------------------------------------------------------------------------- evidence


def evidence(
    hits: list[EvidenceHit] | None,
    *,
    tiers: dict[str, float],
    tier_min: str | None,
    literature: LiteratureSearchResult | None,
    source_ref: str,
) -> CriterionResult:
    """Ordinal tier of the best verified label among the composition's evidence hits, from the
    profile's `tiers` table. Labels outside the table (not_relevant, no_abstract, unclassified)
    are ignored. No usable label is missing with reason `unclassified` and the literature
    counts in a note. `tier_min` excludes a classified candidate whose best tier is below it;
    an unclassified one is flagged, not excluded."""
    usable = [
        h
        for h in (hits or [])
        if h.verified and h.label.value in tiers and h.label in EvidenceLabel
    ]
    counts = (
        f"literature: {literature.matched_with_abstract} works with an abstract of "
        f"{literature.matched_total} matching '{literature.query}'"
        if literature is not None
        else "literature: not searched"
    )
    if not usable:
        return CriterionResult(
            normalized=None,
            source="evidence_labels",
            missing_reason="unclassified",
            flags=(Flag.EVIDENCE_UNCLASSIFIED,),
            caveats=(
                Caveat(
                    id=CaveatId.EVIDENCE_UNCLASSIFIED,
                ),
            ),
            notes=(counts,),
        )
    best = max(usable, key=lambda h: (tiers[h.label.value], h.openalex_id))
    score = tiers[best.label.value]
    if tier_min is not None and tier_min in tiers and score < tiers[tier_min]:
        return CriterionResult(
            normalized=None,
            raw_value=score,
            raw_unit="tier",
            source=best.label.value,
            provenance=best.provenance,
            exclusion=Exclusion(
                rule=ExclusionRule.EVIDENCE_TIER_MIN,
                detail=f"best evidence tier {best.label.value} is below {tier_min}",
                source_ref=source_ref,
            ),
            notes=(counts,),
        )
    return CriterionResult(
        normalized=score,
        raw_value=score,
        raw_unit="tier",
        source=best.label.value,
        provenance=best.provenance,
        notes=(counts,),
    )


# ----------------------------------------------------------------------------- dielectric


def dielectric_constant(
    e_total: Value[float] | None, *, target_band: tuple[float, float] | None
) -> CriterionResult:
    """Target band, not higher-is-better: 1.0 inside `[lo, hi]`, outside it decays linearly to
    0.0 at one band width away. Missing when the source has no DFPT document."""
    if e_total is None or e_total.value is None:
        reason = (
            str(e_total.missing_reason)
            if e_total is not None and e_total.missing_reason
            else str(MissingReason.NOT_COMPUTED)
        )
        return missing(reason, source="mp_dfpt")
    if target_band is None:
        return CriterionResult(
            normalized=None,
            raw_value=e_total.value,
            raw_unit=e_total.unit,
            source=e_total.method,
            provenance=e_total.provenance,
            missing_reason="target band not entered",
        )
    lo, hi = target_band
    width = hi - lo
    v = e_total.value
    distance = lo - v if v < lo else v - hi if v > hi else 0.0
    score = (
        1.0
        if width <= 0 and distance == 0
        else clamp01(1.0 - distance / width)
        if width > 0
        else 0.0
    )
    return CriterionResult(
        normalized=score,
        raw_value=v,
        raw_unit=e_total.unit,
        source=e_total.method,
        provenance=e_total.provenance,
    )


# ----------------------------------------------------------------------------- optional


def deposition_method(
    hits: list[EvidenceHit] | None, *, site_methods: list[str]
) -> CriterionResult:
    """1.0 when any evidence hit names a deposition method in the site's list, 0.0 when hits
    name methods and none match, missing otherwise."""
    named = [h for h in (hits or []) if h.deposition_method]
    if not named or not site_methods:
        return missing("no deposition method stated", source="evidence_labels")
    wanted = {m.lower() for m in site_methods}
    match = next((h for h in named if (h.deposition_method or "").lower() in wanted), None)
    if match is None:
        return CriterionResult(
            normalized=0.0,
            raw_value=0.0,
            raw_unit="match",
            source="evidence_labels",
            notes=(f"methods named: {sorted({h.deposition_method or '' for h in named})}",),
        )
    return CriterionResult(
        normalized=1.0,
        raw_value=1.0,
        raw_unit="match",
        source=match.deposition_method,
        provenance=match.provenance,
    )


def cost() -> CriterionResult:
    """No public cost or abundance source is wired; always missing (documented extension)."""
    return missing("no source wired", source=None)
