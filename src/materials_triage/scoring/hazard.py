"""Hazard criterion: element-level policy first, PubChem GHS second, never a verdict of safe.

Exclusions, in order: radioactive elements (when the effective config excludes them),
exclude-tier elements, acute-toxicity element tiers, acute-toxicity compound tiers, GHS codes
in the acute exclude set. Otherwise the tier is `flag` when an element or compound flag
applies, any GHS code is present, or no PubChem record exists (unknown), and `allow` only when
a record exists with no hazard code in any notification and no element flag. Scores: allow
1.0, flag and unknown 0.5 (the owner's unknown-hazard rule: neutral, never shown as safe).
A hazard record that was never fetched (summary-level pass) is missing, not unknown.

TODO (owner): the list of GHS codes that count as particulate hazards is not sourced; until
it is, the process-hazard caveat fires only on the policy's per-material classifications.
"""

from __future__ import annotations

from materials_triage.records import HazardRecord
from materials_triage.records.bundle import Caveat, CaveatId, Exclusion, ExclusionRule, Flag
from materials_triage.scoring.criteria import CriterionResult, elements_of
from materials_triage.scoring.profile import HazardPolicy

ALLOW = 1.0
NEUTRAL = 0.5


def hazard(
    composition: str,
    record: HazardRecord | None,
    policy: HazardPolicy,
    *,
    exclude_radioactive: bool,
    enrichment_fetched: bool,
    echa_attribution: tuple[str, str] | None,
) -> CriterionResult:
    els = elements_of(composition)
    notes: list[str] = []
    if exclude_radioactive:
        radio = [e for e in els if e in policy.radioactive_elements]
        if radio:
            return _excluded(
                ExclusionRule.HAZARD_RADIOACTIVE,
                f"{', '.join(radio)}: no stable isotope",
                policy.radioactive_source_ref,
            )
    for e in els:
        if e in policy.exclude_elements:
            entry = policy.exclude_elements[e]
            return _excluded(ExclusionRule.HAZARD_EXCLUDE, f"{e}: {entry.reason}", entry.source_ref)
    for e in els:
        tier = policy.acute_element_tiers.get(e)
        if tier is not None and tier.tier == "exclude":
            return _excluded(
                ExclusionRule.HAZARD_ACUTE_ELEMENT, f"{e}: {tier.reason}", tier.source_ref
            )
    comp_tier = policy.acute_compound_tiers.get(composition)
    if comp_tier is not None and comp_tier.tier == "exclude":
        return _excluded(
            ExclusionRule.HAZARD_ACUTE_COMPOUND,
            f"{composition}: GHS codes in the acute exclude set",
            comp_tier.source_ref,
        )
    codes = set(record.h_codes) if record is not None else set()
    hit_exclude = sorted(codes & policy.acute_exclude_codes)
    if hit_exclude:
        return _excluded(
            ExclusionRule.HAZARD_ACUTE_GHS,
            f"{composition}: GHS {', '.join(hit_exclude)} in notifications",
            policy.acute_source_ref,
        )

    flags: list[Flag] = []
    caveats: list[Caveat] = []
    flagged = False
    for e in els:
        if e in policy.flag_elements:
            flagged = True
            flags.append(Flag.HAZARD_FLAG)
            caveats.append(
                Caveat(
                    id=CaveatId.HAZARD_FLAG,
                    subject=e,
                    source_ref=policy.flag_elements[e].source_ref,
                )
            )
        tier = policy.acute_element_tiers.get(e)
        if tier is not None and tier.tier == "flag":
            flagged = True
            flags.append(Flag.HAZARD_FLAG)
            caveats.append(Caveat(id=CaveatId.HAZARD_FLAG, subject=e, source_ref=tier.source_ref))
    if comp_tier is not None and comp_tier.tier == "flag":
        flagged = True
        flags.append(Flag.HAZARD_FLAG)
        caveats.append(
            Caveat(id=CaveatId.HAZARD_FLAG, subject=composition, source_ref=comp_tier.source_ref)
        )
    ref = policy.process_hazard_classifications.get(composition)
    if ref is not None:
        flagged = True
        flags.append(Flag.PROCESS_HAZARD)
        caveats.append(Caveat(id=CaveatId.PROCESS_HAZARD, subject=composition, source_ref=ref))

    if record is None:
        if not enrichment_fetched:
            return CriterionResult(
                normalized=None,
                source="config/hazard_policy.yaml",
                missing_reason="hazard record not fetched",
                flags=tuple(dict.fromkeys(flags)),
                caveats=tuple(caveats),
                notes=("element-level rules applied; PubChem GHS not fetched in this pass",),
            )
        unknown = True
    else:
        unknown = record.cid is None
    if codes:
        flagged = True
        hit_flag = sorted(codes & policy.acute_flag_codes)
        if hit_flag:
            flags.append(Flag.HAZARD_FLAG)
            caveats.append(
                Caveat(
                    id=CaveatId.HAZARD_FLAG, subject=composition, source_ref=policy.acute_source_ref
                )
            )
        else:
            flags.append(Flag.HAZARD_FLAG)
            caveats.append(
                Caveat(
                    id=CaveatId.HAZARD_FLAG, subject=composition, source_ref=policy.acute_source_ref
                )
            )
    if record is not None:
        total = record.notifications_total
        nc = record.notifications_not_classified
        shown = ", ".join(sorted(codes)) if codes else "none"
        if total is not None and nc is not None:
            notes.append(
                f"GHS codes {shown} in {total - nc} of {total} notifications (CID {record.cid})"
            )
        elif total is not None:
            notes.append(f"GHS codes {shown} across {total} notifications (CID {record.cid})")
        else:
            notes.append(f"GHS codes {shown}; notifier counts not reported (CID {record.cid})")
        if record.echa_attribution_required and echa_attribution is not None:
            caveats.append(
                Caveat(
                    id=CaveatId.ATTRIBUTION_ECHA,
                    subject=composition,
                    source_ref=echa_attribution[1],
                )
            )
    if unknown:
        flags.append(Flag.HAZARD_UNKNOWN)
        caveats.append(
            Caveat(
                id=CaveatId.HAZARD_UNKNOWN, subject=composition, source_ref=policy.unknown_rule_ref
            )
        )
        notes.append("no PubChem record: hazard unknown, scored neutral, never shown as safe")
    score = ALLOW if not (flagged or unknown) else NEUTRAL
    return CriterionResult(
        normalized=score,
        raw_value=score,
        raw_unit="tier",
        source="allow" if score == ALLOW else ("unknown" if unknown else "flag"),
        provenance=record.provenance if record is not None else None,
        flags=tuple(dict.fromkeys(flags)),
        caveats=tuple(caveats),
        notes=tuple(notes),
    )


def _excluded(rule: ExclusionRule, detail: str, source_ref: str | None) -> CriterionResult:
    return CriterionResult(
        normalized=None,
        source="config/hazard_policy.yaml",
        exclusion=Exclusion(rule=rule, detail=detail, source_ref=source_ref),
    )
