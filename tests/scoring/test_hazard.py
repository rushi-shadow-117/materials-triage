"""Hazard tiers on recorded PubChem data and the owner's policy."""

from scripts.build_scored_bundle import assemble_groups

from materials_triage.records.bundle import CaveatId, ExclusionRule, Flag
from materials_triage.scoring.hazard import ALLOW, NEUTRAL, hazard


def tier(group, policy, echa, *, radioactive=True):  # type: ignore[no-untyped-def]
    return hazard(
        group.composition,
        group.hazard,
        policy,
        exclude_radioactive=radioactive,
        enrichment_fetched=True,
        echa_attribution=echa,
    )


def test_element_rules_exclude_with_their_source(baseline_groups, policy, echa) -> None:  # type: ignore[no-untyped-def]
    th = tier(baseline_groups["ThO2"], policy, echa)
    assert th.exclusion is not None and th.exclusion.rule is ExclusionRule.HAZARD_RADIOACTIVE
    assert th.exclusion.source_ref == "hazard_policy.yaml#tiers.radioactive_exclude"
    be = tier(baseline_groups["BeO"], policy, echa)
    assert be.exclusion is not None and be.exclusion.rule is ExclusionRule.HAZARD_EXCLUDE
    assert be.exclusion.source_ref == "hazard_policy.yaml#tiers.exclude.Be"
    # with the radioactive exclusion off, ThO2 falls through to its GHS codes (H301, H311, H331)
    th2 = tier(baseline_groups["ThO2"], policy, echa, radioactive=False)
    assert th2.exclusion is None and th2.normalized == NEUTRAL and Flag.HAZARD_FLAG in th2.flags


def test_cd_and_pb_yim_entries_are_excluded(policy, echa) -> None:  # type: ignore[no-untyped-def]
    groups = assemble_groups(["CdTiO3", "Cd2Ta2O7", "PbHfO3", "PbZrO3"])
    rules = {k: tier(g, policy, echa).exclusion for k, g in groups.items()}
    assert {k: r.rule for k, r in rules.items() if r} == {
        "TiCdO3": ExclusionRule.HAZARD_EXCLUDE,
        "Ta2Cd2O7": ExclusionRule.HAZARD_EXCLUDE,
        "HfPbO3": ExclusionRule.HAZARD_ACUTE_ELEMENT,
        "ZrPbO3": ExclusionRule.HAZARD_ACUTE_ELEMENT,
    }
    assert rules["HfPbO3"].source_ref == "hazard_policy.yaml#tiers.acute_toxicity.element_tiers.Pb"  # type: ignore[union-attr]


def test_allow_flag_and_unknown_scores(baseline_groups, policy, echa) -> None:  # type: ignore[no-untyped-def]
    hf = tier(baseline_groups["HfO2"], policy, echa)
    assert hf.normalized == ALLOW and hf.source == "allow" and not hf.flags
    assert any("in 7 of 344 notifications" in n for n in hf.notes)
    assert {c.id for c in hf.caveats} == {CaveatId.ATTRIBUTION_ECHA}
    ba = tier(baseline_groups["BaTiO3"], policy, echa)
    assert ba.normalized == NEUTRAL and Flag.HAZARD_FLAG in ba.flags
    assert any(c.id is CaveatId.HAZARD_FLAG and c.subject == "Ba" for c in ba.caveats)
    si = tier(baseline_groups["SiO2"], policy, echa)
    assert si.normalized == NEUTRAL and Flag.PROCESS_HAZARD in si.flags
    assert any(c.id is CaveatId.PROCESS_HAZARD and c.subject == "SiO2" for c in si.caveats)
    al = tier(baseline_groups["Al2O3"], policy, echa)
    assert al.normalized == NEUTRAL and Flag.HAZARD_FLAG in al.flags  # H335, H372 present


def test_no_record_is_unknown_and_not_fetched_is_missing(baseline_groups, policy, echa) -> None:  # type: ignore[no-untyped-def]
    g = baseline_groups["HfO2"]
    unknown = hazard(
        g.composition,
        g.hazard.model_copy(update={"cid": None, "h_codes": [], "notifications_total": None}),  # type: ignore[union-attr]
        policy,
        exclude_radioactive=True,
        enrichment_fetched=True,
        echa_attribution=echa,
    )
    assert unknown.normalized == NEUTRAL and Flag.HAZARD_UNKNOWN in unknown.flags
    assert unknown.source == "unknown"
    not_fetched = hazard(
        "HfO2",
        None,
        policy,
        exclude_radioactive=True,
        enrichment_fetched=False,
        echa_attribution=echa,
    )
    assert (
        not_fetched.normalized is None and not_fetched.missing_reason == "hazard record not fetched"
    )
    assert not_fetched.exclusion is None
    # element rules still apply without a record
    th = hazard(
        "ThO2",
        None,
        policy,
        exclude_radioactive=True,
        enrichment_fetched=False,
        echa_attribution=echa,
    )
    assert th.exclusion is not None and th.exclusion.rule is ExclusionRule.HAZARD_RADIOACTIVE
