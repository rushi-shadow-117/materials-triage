"""Template tokens: the only way a number, formula, rank, or id reaches rendered text.

The LLM writes `{formula:HfO2}` or `{value:HfO2:band_gap}`; the renderer fills them from the
bundle. The verifier validates the same tokens with the same index, so a token the renderer
could not fill never survives verification.

Grammar: `{kind:arg}` or `{kind:composition:field}` with kind in TOKEN_KINDS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from materials_triage.records.bundle import (
    Anchor,
    Candidate,
    CriterionScore,
    PolymorphSummaryRow,
    ProvenanceBundle,
)
from materials_triage.render import precision

TOKEN_KINDS = (
    "formula",
    "rank",
    "value",
    "source",
    "criterion",
    "count",
    "ghs",
    "spacegroup",
    "id",
)
TOKEN_RE = re.compile(r"\{(" + "|".join(TOKEN_KINDS) + r"):([^{}]*)\}")

CRITERION_LABELS: dict[str, str] = {
    "stability": "stability (energy above hull)",
    "band_gap": "band gap",
    "hazard": "hazard",
    "simplicity": "simplicity",
    "evidence": "evidence",
    "dielectric_constant": "dielectric constant",
    "deposition_method": "deposition method",
    "cost": "cost",
}
COUNT_FIELDS = (
    "polymorphs",
    "observed",
    "theoretical",
    "unknown",
    "hits",
    "matched",
    "with_abstract",
    "gap_values",
    "notifications",
)


class TokenError(ValueError):
    """A token the bundle cannot fill. `kind` is the VerifierFailure kind."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class BundleIndex:
    rows: dict[str, Candidate | Anchor] = field(default_factory=dict)
    ids: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, bundle: ProvenanceBundle) -> BundleIndex:
        idx = cls()
        rows: list[Candidate | Anchor] = [*bundle.candidates, *bundle.anchors]
        for row in rows:
            idx.rows[row.composition] = row
            g = row.group
            summary = g.polymorphs
            for prow in [
                summary.ground_state,
                summary.lowest_observed,
                summary.scored,
                *summary.top_by_hull,
            ]:
                if prow is None:
                    continue
                idx._add_row_ids(prow)
            if g.hazard is not None:
                if g.hazard.cid is not None:
                    idx.ids.add(f"CID:{g.hazard.cid}")
                idx.ids.add(g.hazard.provenance.source_record_id)
            if g.literature is not None:
                for hit in g.literature.hits:
                    idx.ids.add(hit.openalex_id)
                    idx.ids.add(hit.openalex_id.rsplit("/", 1)[-1])
                    if hit.doi:
                        idx.ids.add(hit.doi)
                        idx.ids.add(hit.doi.removeprefix("https://doi.org/"))
                    idx.ids.add(hit.provenance.source_record_id)
            if g.experimental_gaps is not None:
                for v in g.experimental_gaps.values:
                    idx.ids.add(v.value_ev.provenance.source_record_id)
            for ref in g.reference_values:
                idx.ids.add(ref.entry_id)
                idx.ids.add(ref.provenance.source_record_id)
            if row.score is not None:
                for cs in row.score.criteria:
                    if cs.provenance is not None:
                        idx.ids.add(cs.provenance.source_record_id)
        for ev in bundle.evidence:
            idx.ids.add(ev.openalex_id)
            idx.ids.add(ev.provenance.source_record_id)
        return idx

    def _add_row_ids(self, prow: PolymorphSummaryRow) -> None:
        if prow.mp_id:
            self.ids.add(prow.mp_id)
        if prow.jarvis_jid:
            self.ids.add(prow.jarvis_jid)
        for values in (prow.band_gap, prow.dielectric):
            for v in values.values():
                self.ids.add(v.provenance.source_record_id)
        if prow.hull_energy is not None:
            self.ids.add(prow.hull_energy.provenance.source_record_id)

    def row(self, composition: str) -> Candidate | Anchor:
        try:
            return self.rows[composition]
        except KeyError:
            raise TokenError(
                "formula_not_in_bundle", f"{composition} is not a composition in this bundle"
            ) from None

    def criterion(self, composition: str, name: str) -> CriterionScore:
        row = self.row(composition)
        if name not in CRITERION_LABELS:
            raise TokenError("unknown_token", f"unknown criterion {name!r}")
        if row.score is None:
            raise TokenError("unknown_token", f"{composition} has no score breakdown")
        for cs in row.score.criteria:
            if cs.criterion == name:
                return cs
        raise TokenError("unknown_token", f"{composition} has no {name} criterion")


def _split(arg: str, parts: int, token: str) -> list[str]:
    bits = arg.split(":")
    if len(bits) != parts:
        raise TokenError("unknown_token", f"malformed token {{{token}}}")
    return bits


def ghs_text(row: Candidate | Anchor) -> str:
    """The owner's display rule: codes in M of N notifications, never a verdict."""
    h = row.group.hazard
    if h is None:
        return "no PubChem record; hazard unknown"
    codes = ", ".join(h.h_codes) if h.h_codes else None
    total = h.notifications_total
    if total is None:
        if codes:
            return f"GHS codes {codes} reported; notification counts not available"
        return "no GHS notification counts available; hazard unknown"
    classified = (
        total - h.notifications_not_classified
        if h.notifications_not_classified is not None
        else None
    )
    m = precision.quantize(classified, 0) if classified is not None else "an unreported number"
    n = precision.quantize(total, 0)
    if codes:
        return f"GHS codes {codes} in {m} of {n} notifications"
    return f"no GHS hazard codes in {n} notifications"


def resolve(index: BundleIndex, kind: str, arg: str, *, units: str = "eV") -> str:
    """Fill one token. Raises TokenError when the bundle cannot back it."""
    token = f"{kind}:{arg}"
    if kind == "formula":
        return index.row(arg).composition
    if kind == "rank":
        row = index.row(arg)
        if isinstance(row, Anchor):
            if row.would_rank is None:
                return "unranked anchor"
            return f"would rank {row.would_rank} of {row.out_of}"
        if row.rank is None:
            return "excluded" if row.excluded is not None else "unranked"
        return str(row.rank)
    if kind == "value":
        comp, name = _split(arg, 2, token)
        cs = index.criterion(comp, name)
        if cs.raw_value is None:
            reason = cs.missing_reason or "not reported"
            return f"missing ({reason})"
        return precision.fmt(cs.raw_value, cs.raw_unit, units)
    if kind == "source":
        comp, name = _split(arg, 2, token)
        return index.criterion(comp, name).source or "no source"
    if kind == "criterion":
        if arg not in CRITERION_LABELS:
            raise TokenError("unknown_token", f"unknown criterion {arg!r}")
        return CRITERION_LABELS[arg]
    if kind == "count":
        comp, fld = _split(arg, 2, token)
        return _count(index.row(comp), fld, token)
    if kind == "ghs":
        return ghs_text(index.row(arg))
    if kind == "spacegroup":
        gs = index.row(arg).group.polymorphs.ground_state
        if gs is None or gs.spacegroup_symbol is None:
            return "space group not reported"
        return gs.spacegroup_symbol
    if kind == "id":
        if arg not in index.ids:
            raise TokenError("unknown_record_id", f"{arg} is not a record id in this bundle")
        return arg
    raise TokenError("unknown_token", f"unknown token kind {kind!r}")


def _count(row: Candidate | Anchor, fld: str, token: str) -> str:
    g = row.group
    p = g.polymorphs
    lit = g.literature
    gaps = g.experimental_gaps
    value: int | None
    match fld:
        case "polymorphs":
            value = p.total
        case "observed":
            value = p.observed_count
        case "theoretical":
            value = p.theoretical_count
        case "unknown":
            value = p.unknown_count
        case "hits":
            value = len(lit.hits) if lit else 0
        case "matched":
            value = lit.matched_total if lit else None
        case "with_abstract":
            value = lit.matched_with_abstract if lit else None
        case "gap_values":
            value = gaps.n if gaps else 0
        case "notifications":
            value = g.hazard.notifications_total if g.hazard else None
        case _:
            raise TokenError("unknown_token", f"unknown count field in {{{token}}}")
    return "not reported" if value is None else precision.quantize(value, 0)


def render_text(index: BundleIndex, text: str, *, units: str = "eV") -> str:
    """Fill every token in `text`. Raises TokenError on the first one the bundle cannot fill;
    verified text never raises because the verifier already removed those sentences."""
    return TOKEN_RE.sub(lambda m: resolve(index, m.group(1), m.group(2), units=units), text)
