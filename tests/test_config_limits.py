"""The one candidate splitter and the core input limits (Track H, item 3)."""

from __future__ import annotations

import pytest

from materials_triage.config.limits import (
    LimitExceededError,
    candidate_entries,
    check_request_limits,
    split_candidate_text,
)
from materials_triage.config.schema import CoreConfig


def test_split_accepts_commas_semicolons_and_new_lines() -> None:
    assert split_candidate_text("HfO2; ZrO2\nAl2O3, hafnia") == ["HfO2", "ZrO2", "Al2O3", "hafnia"]


def test_split_drops_blanks_and_keeps_the_first_spelling_of_a_repeat() -> None:
    assert split_candidate_text(" HfO2 ,, ;\n\n hfo2 ; Hf O2 ") == ["HfO2", "Hf O2"]
    assert split_candidate_text("") == []
    assert split_candidate_text(" ,;\n") == []


def test_candidate_entries_prefers_typed_text_over_a_list() -> None:
    assert candidate_entries({"candidate_text": "a; b", "candidate_list": ["x"]}) == ["a", "b"]
    assert candidate_entries({"candidate_list": ["x", 2]}) == ["x", "2"]
    assert candidate_entries({}) == []


def test_request_limit_is_exact() -> None:
    core = CoreConfig()
    check_request_limits(core, request_text="x" * core.max_request_chars)
    with pytest.raises(LimitExceededError) as e:
        check_request_limits(core, request_text="x" * (core.max_request_chars + 1))
    assert str(e.value) == (
        "The request is 2,001 characters; the limit is 2,000. Shorten it and try again."
    )


def test_candidate_limit_is_exact_for_text_and_for_a_list() -> None:
    core = CoreConfig()
    names = [f"X{i}" for i in range(core.max_candidates)]
    check_request_limits(core, settings={"candidate_list": names})
    check_request_limits(core, settings={"candidate_text": "; ".join(names)})
    with pytest.raises(LimitExceededError) as e:
        check_request_limits(core, settings={"candidate_list": [*names, "one more"]})
    assert str(e.value) == "51 candidates were given; the limit is 50. Remove some and try again."
    with pytest.raises(LimitExceededError):
        check_request_limits(core, settings={"candidate_text": ", ".join([*names, "one more"])})
