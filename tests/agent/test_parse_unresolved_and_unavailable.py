"""Unparseable candidate names are reported as not found and the run proceeds; requested
properties no configured source covers are carried as unavailable (Track F, C5 and B4)."""

from __future__ import annotations

import pytest

from materials_triage.agent import parse
from materials_triage.agent.tools import ParsedRequest
from materials_triage.config import schema as cs


def test_split_keeps_order_and_reports_names_that_are_not_formulas() -> None:
    resolved, unresolved = parse.split_candidates(
        ["HfO2", "Unobtainium oxide", "ZrO2", "HfO2", "Unobtainium oxide"]
    )
    assert resolved == ["HfO2", "ZrO2"] and unresolved == ["Unobtainium oxide"]
    with pytest.raises(parse.CandidateListError):
        parse.normalize_candidates(["HfO2", "Unobtainium oxide"])


def test_to_query_settings_proceeds_with_the_resolved_names() -> None:
    parsed = ParsedRequest(mode="candidate_list", candidate_list=["HfO2", "Unobtainium oxide"])
    query, _, unresolved = parse.to_query_settings(parsed, profile="p")
    assert query.candidate_list == ["HfO2"] and unresolved == ["Unobtainium oxide"]
    with pytest.raises(parse.CandidateListError):
        parse.to_query_settings(
            ParsedRequest(mode="candidate_list", candidate_list=["Unobtainium oxide"]), profile="p"
        )


def test_unavailable_properties_are_the_names_no_criterion_covers() -> None:
    assert cs.unavailable_properties(
        ["Band gap", "conductivity", "thermal  conductivity", "k", "conductivity"]
    ) == ["conductivity", "thermal conductivity"]
    assert set(cs.PROPERTY_CRITERIA.values()) <= set(cs.CRITERIA)


def test_handler_carries_both_lists_to_the_outcome() -> None:
    paths = cs.default_paths()
    profile, _ = cs.scoring_profile_from_yaml(paths["scoring_profile"])
    site = cs.site_profile_from_yaml(paths["site_profile"])
    handler = parse.make_handler(
        core=cs.CoreConfig(), site=site, profile=profile, cli_profile=profile.name
    )
    out = handler(
        ParsedRequest(
            mode="candidate_list",
            candidate_list=["HfO2", "sapphire glass"],
            requested_properties=["conductivity", "band gap"],
        )
    )
    outcome = out.data
    assert isinstance(outcome, parse.ParseOutcome)
    assert outcome.unresolved_candidates == ["sapphire glass"]
    assert outcome.unavailable_properties == ["conductivity"]


def _handled(**fields: object) -> parse.ParseOutcome:
    paths = cs.default_paths()
    profile, _ = cs.scoring_profile_from_yaml(paths["scoring_profile"])
    site = cs.site_profile_from_yaml(paths["site_profile"])
    handler = parse.make_handler(
        core=cs.CoreConfig(), site=site, profile=profile, cli_profile=profile.name
    )
    out = handler(ParsedRequest(**fields))  # type: ignore[arg-type]
    assert isinstance(out.data, parse.ParseOutcome)
    return out.data


def test_a_request_naming_no_chemistry_and_no_property_is_clarified_in_code() -> None:
    """C1: whatever the model chose, a discovery request with nothing to search on asks."""
    vague = _handled(mode="discovery")
    assert vague.missing_required == parse.CLARIFY_FIELDS and not vague.ready
    assert _handled(mode="discovery", requested_chemistry=["oxide"]).missing_required == []
    assert _handled(mode="discovery", requested_properties=["band gap"]).missing_required == []
    assert _handled(mode="discovery", band_gap_min_ev=4.0).missing_required == []
    assert _handled(mode="discovery", verbosity="concise").missing_required == []  # follow-up
    assert _handled(mode="candidate_list", candidate_list=["HfO2"]).missing_required == []
