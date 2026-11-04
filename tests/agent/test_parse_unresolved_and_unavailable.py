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


def test_names_and_lowercase_formulas_match_the_synonym_table() -> None:
    """Human test session, item 11: "hafnia" and "hfo2" match HfO2 through the profile's
    synonym table; anything else is reported with a reason, never as a Python list."""
    from materials_triage.agent import parse

    synonyms = {"HfO2": ["hafnia", "hafnium dioxide"], "ZrO2": ["zirconia"]}
    out, bad = parse.split_candidates(
        ["hfo2", "Hafnia", "HAFNIUM  DIOXIDE", "zirconia", "hafnia??", "sapphire glass"], synonyms
    )
    assert out == ["HfO2", "ZrO2"] and bad == ["hafnia??", "sapphire glass"]
    # capitals that are not element symbols never become an invented compound
    assert parse.split_candidates(
        ["SAPPHIRE", "HAFNIA", "HFO2", "Al2O3", "Ba0.5Sr0.5TiO3"], synonyms
    ) == (
        ["HfO2", "Al2O3", "Ba0.5Sr0.5Ti1O3"],
        ["SAPPHIRE"],
    )
    with pytest.raises(parse.CandidateListError) as e:
        parse.normalize_candidates(["hafnia??"], synonyms)
    assert "[" not in str(e.value) and "hafnia??" in str(e.value)


def test_an_all_unmatched_list_is_missing_not_an_error(layers) -> None:  # type: ignore[no-untyped-def]
    from materials_triage.agent import parse

    core, site, profile = layers
    outcome = parse.parse_from_settings(
        {"mode": "candidate_list", "candidate_list": ["hafnia??", "sapphire glass"]},
        core=core,
        site=site,
        profile=profile,
        cli_profile=profile.name,
    )
    assert outcome.unresolved_candidates == ["hafnia??", "sapphire glass"]
    assert outcome.missing_required == ["candidate_list"]
    assert "[" not in parse.nothing_matched(outcome.unresolved_candidates)
