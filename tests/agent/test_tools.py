"""Tool contracts: strict schemas, closed inputs, fixed enums."""

from typing import Any

import pytest

from materials_triage.agent import tools
from materials_triage.config.schema import CRITERIA, RefusalPolicy
from materials_triage.records.bundle import EvidenceLabel


def _every_object(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            found.append(node)
        for v in node.values():
            found.extend(_every_object(v))
    elif isinstance(node, list):
        for v in node:
            found.extend(_every_object(v))
    return found


def test_every_tool_schema_is_strict() -> None:
    for name, (spec, _model) in tools.TOOLS.items():
        assert spec.name == name
        text = str(spec.input_schema)
        assert "$ref" not in text and "$defs" not in text and "default" not in text, name
        objects = _every_object(spec.input_schema)
        assert objects, name
        for obj in objects:
            assert obj["additionalProperties"] is False
            assert obj["required"] == list(obj["properties"])


def test_only_the_four_tools_exist() -> None:
    assert list(tools.TOOLS) == [
        "parse_request",
        "classify_abstract",
        "write_rationale",
        "propose_relaxation",
    ]


def test_inputs_reject_extra_keys_and_unknown_tools() -> None:
    with pytest.raises(tools.ToolInputError, match="Extra"):
        tools.validate_input("parse_request", {"mode": "discovery", "score": 1.0})
    with pytest.raises(tools.ToolInputError, match="unknown tool"):
        tools.validate_input("fetch_url", {})
    with pytest.raises(tools.ToolInputError, match="label"):
        tools.validate_input(
            "classify_abstract",
            {"label": "unclassified", "deposition_method": "ALD", "supporting_sentence": "x"},
        )


def test_weights_are_named_fields_covering_every_criterion() -> None:
    assert tuple(tools.WeightOverrides.model_fields) == CRITERIA
    w = tools.WeightOverrides(band_gap=0.5)
    assert w.as_dict() == {"band_gap": 0.5}


def test_out_of_scope_values_are_the_refusal_policy_attributes() -> None:
    assert {v.value for v in tools.OutOfScope} == set(RefusalPolicy.model_fields)


def test_classifier_labels_are_the_evidence_labels_minus_unclassified() -> None:
    assert {v.value for v in tools.ClassifierLabel} == {
        v.value for v in EvidenceLabel if v is not EvidenceLabel.UNCLASSIFIED
    }


def test_deposition_enum_is_the_owner_list() -> None:
    assert [m.value for m in tools.DepositionMethod] == [
        "ALD",
        "PEALD",
        "sputtering",
        "PLD",
        "CVD",
        "MOCVD",
        "evaporation",
        "sol_gel",
        "MBE",
        "other",
        "unknown",
    ]


def test_parsed_request_nulls_mean_not_stated() -> None:
    parsed = tools.validate_input("parse_request", {"band_gap_min_ev": 5.0})
    assert isinstance(parsed, tools.ParsedRequest)
    assert parsed.mode is None and parsed.top_n is None and parsed.weights.as_dict() == {}
