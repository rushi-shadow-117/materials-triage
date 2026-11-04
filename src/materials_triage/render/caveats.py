"""Caveat ids resolve to text from config entries with status `entered`.

Chemistry caveats (hazard, stability, band offsets) come from the owner's config files and
are never written here. Data-state caveats describe what this run did or lacked; their text
is code-owned because it states system behavior, not chemistry. An id with no entered text
renders a visible marker, never invented prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from materials_triage.config.schema import default_paths, load_yaml
from materials_triage.records.bundle import Anchor, Candidate, Caveat, CaveatId

NOT_ENTERED = "caveat text not entered: {id}"

# Caveats every row of a profile or run carries by construction. They show once above the
# results table, never per row, and never in a row's rationale or key caveat.
PROFILE_WIDE: frozenset[CaveatId] = frozenset(
    {
        CaveatId.BAND_OFFSETS_NOT_CHECKED,
        CaveatId.STABILITY_CUTOFF_HULL_MISMATCH,
        CaveatId.STABILITY_CUTOFF_OXIDE_CALIBRATED,
        CaveatId.EVIDENCE_UNCLASSIFIED,
        CaveatId.ATTRIBUTION_ECHA,
    }
)


def row_specific(caveats: list[Caveat]) -> list[Caveat]:
    """The row's own caveats, first of each id, in the row's order."""
    seen: set[CaveatId] = set()
    out: list[Caveat] = []
    for c in caveats:
        if c.id in PROFILE_WIDE or c.id in seen:
            continue
        seen.add(c.id)
        out.append(c)
    return out


SYSTEM_TEXT: dict[CaveatId, str] = {
    CaveatId.EXPERIMENTAL_GAP_COMPOSITION_LEVEL: (
        "The experimental band gap is reported for the composition, not for a specific polymorph."
    ),
    CaveatId.EXPERIMENTAL_GAP_UNREFERENCED: (
        "The experimental band gap table does not cite a primary source for this value."
    ),
    CaveatId.REFERENCE_VALUE_PENDING: (
        "A reference value exists for this composition but its source is not yet verified; "
        "it is shown as missing."
    ),
    CaveatId.ANION_UNDETERMINED: "The anion policy could not be evaluated for this composition.",
    CaveatId.EVIDENCE_UNCLASSIFIED: (
        "Literature evidence was not classified in this run; the evidence criterion used no labels."
    ),
    CaveatId.ENRICHMENT_MISSING: (
        "Only summary-level data was fetched for this candidate; the cross-checks did not run."
    ),
    # owner-approved texts, 2026-11-04 (human test session fix batch, item 8)
    CaveatId.BAND_GAP_CONFLICT: (
        "The experimental and computed band gaps disagree beyond the profile's tolerance; "
        "see the audit view."
    ),
    CaveatId.NEAR_CUTOFF: "Energy above hull is close to this profile's stability cutoff.",
    CaveatId.GROUND_STATE_IS_THEORETICAL: (
        "The lowest-energy polymorph on record is computed, not observed."
    ),
}

# The key caveat is the first present in this order, then the row's others in enum order.
KEY_PRIORITY: tuple[CaveatId, ...] = (
    CaveatId.HAZARD_FLAG,
    CaveatId.BAND_GAP_CONFLICT,
    CaveatId.PBE_ONLY_BELOW_WINDOW,
    CaveatId.NEAR_CUTOFF,
    CaveatId.GROUND_STATE_IS_THEORETICAL,
)
NO_KEY_CAVEAT = "none specific to this row"


def key_caveat(caveats: list[Caveat]) -> Caveat | None:
    """The most row-specific caveat, or None when the row has only profile-wide ones."""
    own = row_specific(caveats)
    for cid in KEY_PRIORITY:
        hit = next((c for c in own if c.id is cid), None)
        if hit is not None:
            return hit
    return own[0] if own else None


@dataclass(frozen=True)
class CaveatText:
    id: CaveatId
    subject: str | None
    text: str
    source: str  # config path or "system"
    entered: bool


def _entered(node: Any) -> bool:
    return isinstance(node, dict) and node.get("status") == "entered"


class CaveatConfig:
    """The two config files that hold caveat text, loaded once."""

    def __init__(
        self,
        hazard_policy: dict[str, Any],
        profile: dict[str, Any],
        site: dict[str, Any] | None = None,
    ) -> None:
        self.hazard = hazard_policy
        self.profile = profile
        self.site = site or {}

    @classmethod
    def load(cls, profile_path: Path | None = None) -> CaveatConfig:
        paths = default_paths()
        return cls(
            load_yaml(paths["hazard_policy"]),
            load_yaml(profile_path or paths["scoring_profile"]),
            load_yaml(paths["site_profile"]),
        )

    def _profile_criterion(self, name: str, key: str) -> str | None:
        node = (self.profile.get("criteria") or {}).get(name) or {}
        if _entered(node) and isinstance(node.get(key), str):
            return str(node[key])
        return None

    def _hazard_flag(self, subject: str | None) -> tuple[str, str] | None:
        tiers = self.hazard.get("tiers") or {}
        for entry in (tiers.get("flag") or {}).get("entries") or []:
            if _entered(entry) and entry.get("element") == subject and entry.get("flag_text"):
                return str(entry["flag_text"]), f"hazard_policy.yaml#tiers.flag.{subject}"
        acute = tiers.get("acute_toxicity") or {}
        for entry in acute.get("element_tiers") or []:
            if _entered(entry) and entry.get("element") == subject and entry.get("tier") == "flag":
                return str(entry["reason"]), f"hazard_policy.yaml#acute_toxicity.element.{subject}"
        for entry in acute.get("compound_tiers") or []:
            if (
                _entered(entry)
                and entry.get("composition") == subject
                and entry.get("tier") in ("flag", "unknown")
            ):
                text = entry.get("note") or f"GHS codes matched: {entry.get('codes_matched')}"
                return str(text), f"hazard_policy.yaml#acute_toxicity.compound.{subject}"
        return None

    def _ghs_flag_set(self, row: Candidate | Anchor | None) -> tuple[str, str] | None:
        """A composition flagged through the GHS flag set: the entered template filled from
        the row's PubChem record (codes in the set, M classified of N notifications)."""
        tiers = self.hazard.get("tiers") or {}
        node = tiers.get("ghs_flag_codes") or {}
        template = node.get("caveat_template") or {}
        if row is None or not _entered(node) or not _entered(template):
            return None
        hazard = row.group.hazard
        if hazard is None:
            return None
        flag_codes = {str(c) for c in node.get("codes") or []}
        acute = (tiers.get("acute_toxicity") or {}).get("rule") or {}
        flag_codes |= {str(c) for c in acute.get("flag_if_any") or []}
        codes = sorted(set(hazard.h_codes) & flag_codes)
        if not codes:
            return None
        total = hazard.notifications_total
        classified = (
            total - hazard.notifications_not_classified
            if total is not None and hazard.notifications_not_classified is not None
            else None
        )
        text = (
            str(template["text"])
            .replace("{codes}", ", ".join(codes))
            .replace("{M}", str(classified) if classified is not None else "an unreported number")
            .replace("{N}", str(total) if total is not None else "an unreported number")
        )
        return text, "hazard_policy.yaml#tiers.ghs_flag_codes.caveat_template"

    def _process_hazard(self, subject: str | None) -> tuple[str, str] | None:
        node = (self.hazard.get("tiers") or {}).get("process_hazard") or {}
        template = node.get("caveat_template") or {}
        if not _entered(template):
            return None
        specific = ""
        for entry in node.get("material_classifications") or []:
            if _entered(entry) and entry.get("composition") == subject:
                specific = str(entry["text"])
        text = str(template["text"]).replace("{material_specific_classification}", specific)
        return " ".join(text.split()), "hazard_policy.yaml#tiers.process_hazard"

    def _echa(self) -> tuple[str, str] | None:
        site_entry = (self.site.get("attribution") or {}).get("echa")
        if (
            isinstance(site_entry, dict)
            and _entered(site_entry)
            and isinstance(site_entry.get("text"), str)
        ):
            return str(site_entry["text"]), "site_profile.default.yaml#attribution.echa"
        for key in ("attribution_echa", "echa_attribution", "attribution"):
            node = self.hazard.get(key)
            if isinstance(node, dict) and key == "attribution":
                node = node.get("echa")
            if isinstance(node, dict) and _entered(node) and isinstance(node.get("text"), str):
                return str(node["text"]), f"hazard_policy.yaml#{key}"
        return None

    def resolve(self, caveat: Caveat, row: Candidate | Anchor | None = None) -> CaveatText:
        """`row` lets a template fill in the row's own record (the GHS flag set caveat)."""
        cid, subject = caveat.id, caveat.subject
        found: tuple[str, str] | None = None
        if cid is CaveatId.BAND_OFFSETS_NOT_CHECKED:
            text = self._profile_criterion("band_gap", "standing_caveat")
            found = (text, "scoring_profile#criteria.band_gap.standing_caveat") if text else None
        elif cid is CaveatId.STABILITY_CUTOFF_HULL_MISMATCH:
            text = self._profile_criterion("stability", "caveat")
            found = (text, "scoring_profile#criteria.stability.caveat") if text else None
        elif cid is CaveatId.STABILITY_CUTOFF_OXIDE_CALIBRATED:
            text = self._profile_criterion("stability", "anion_calibration_caveat")
            found = (
                (text, "scoring_profile#criteria.stability.anion_calibration_caveat")
                if text
                else None
            )
        elif cid is CaveatId.PBE_ONLY_BELOW_WINDOW:
            text = self._profile_criterion("band_gap", "pbe_only_caveat")
            found = (text, "scoring_profile#criteria.band_gap.pbe_only_caveat") if text else None
        elif cid is CaveatId.HAZARD_FLAG:
            found = self._hazard_flag(subject) or self._ghs_flag_set(row)
        elif cid is CaveatId.HAZARD_UNKNOWN:
            node = self.hazard.get("unknown_hazard_rule") or {}
            if _entered(node):
                found = (str(node["description"]), "hazard_policy.yaml#unknown_hazard_rule")
        elif cid is CaveatId.PROCESS_HAZARD:
            found = self._process_hazard(subject)
        elif cid is CaveatId.ATTRIBUTION_ECHA:
            found = self._echa()
        elif cid in SYSTEM_TEXT:
            found = (SYSTEM_TEXT[cid], "system")
        if found is None:
            return CaveatText(cid, subject, NOT_ENTERED.format(id=cid.value), "none", False)
        return CaveatText(cid, subject, found[0], found[1], True)
