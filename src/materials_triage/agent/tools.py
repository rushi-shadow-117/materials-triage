"""The four tools the model may call, and no others.

Each tool's input is a Pydantic model (extra keys rejected) turned into a strict JSON schema:
no $ref, every object closed, every property required (optional ones are nullable). The
handlers that act on validated inputs live with their steps; this module owns the contract.
"""

from __future__ import annotations

import copy
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from materials_triage.config.schema import Strict, Terminology, Units, Verbosity, View
from materials_triage.records.bundle import EvidenceLabel

from .llm import ToolSpec


class DepositionMethod(StrEnum):
    """Code-owned (owner's list, Track B prompt). The site profile's pending list is not read."""

    ALD = "ALD"
    PEALD = "PEALD"
    SPUTTERING = "sputtering"
    PLD = "PLD"
    CVD = "CVD"
    MOCVD = "MOCVD"
    EVAPORATION = "evaporation"
    SOL_GEL = "sol_gel"
    MBE = "MBE"
    OTHER = "other"
    UNKNOWN = "unknown"


class OutOfScope(StrEnum):
    """Exactly the attribute names of config.schema.RefusalPolicy."""

    WETLAB = "wetlab"
    PRIVATE_DATA = "private_data"
    ESTIMATES = "estimates"
    CONFIG_CHANGE = "config_change"


class ClassifierLabel(StrEnum):
    """EvidenceLabel minus `unclassified`, which only no-LLM mode assigns."""

    COMPUTED_ONLY = EvidenceLabel.COMPUTED_ONLY.value
    BULK_SYNTHESIZED = EvidenceLabel.BULK_SYNTHESIZED.value
    THIN_FILM_DEPOSITED = EvidenceLabel.THIN_FILM_DEPOSITED.value
    DIELECTRIC_CHARACTERIZED = EvidenceLabel.DIELECTRIC_CHARACTERIZED.value
    NOT_RELEVANT = EvidenceLabel.NOT_RELEVANT.value
    NO_ABSTRACT = EvidenceLabel.NO_ABSTRACT.value


# ------------------------------------------------------------------------------ inputs


# The scoring criteria by name; a test keeps this equal to config.schema.CRITERIA.
CriterionName = Literal[
    "stability",
    "band_gap",
    "hazard",
    "simplicity",
    "evidence",
    "dielectric_constant",
    "deposition_method",
    "cost",
]


class WeightSetting(Strict):
    """One weight the request states. A list of these replaces one nullable field per
    criterion: the strict tool schema allows at most 16 union-typed parameters (API limit),
    and a list states only what the request says (Track G)."""

    criterion: CriterionName
    weight: float


def weights_dict(settings: list[WeightSetting]) -> dict[str, float]:
    out: dict[str, float] = {}
    for w in settings:
        name = str(w.criterion)
        if name in out:
            raise ValueError(f"weight for {name} given twice")
        out[name] = w.weight
    return out


class ParsedRequest(Strict):
    """QuerySettings without `profile` (a CLI choice), plus what the parser could not find."""

    mode: Literal["discovery", "candidate_list"] | None = None
    candidate_list: list[str] = Field(default_factory=list)
    top_n: int | None = None
    weights: list[WeightSetting] = Field(default_factory=list)  # only weights stated
    band_gap_min_ev: float | None = None
    band_gap_max_ev: float | None = None
    max_elements: int | None = None
    evidence_tier_min: str | None = None
    e_above_hull_max_mev: float | None = None
    extra_anchors: list[str] = Field(default_factory=list)
    exclude_radioactive: bool | None = None
    verbosity: Verbosity | None = None
    terminology: Terminology | None = None
    units: Units | None = None
    view: View | None = None
    requested_properties: list[str] = Field(default_factory=list)  # as the request names them
    requested_chemistry: list[str] = Field(default_factory=list)  # elements, oxides, nitrides
    missing_required: list[str] = Field(default_factory=list)
    out_of_scope: OutOfScope | None = None


class ClassifyAbstract(Strict):
    label: ClassifierLabel
    deposition_method: DepositionMethod
    supporting_sentence: str | None


class RationaleSlotText(Strict):
    slot: str
    text: str


class WriteRationale(Strict):
    slots: list[RationaleSlotText]


class ProposeRelaxation(Strict):
    choice_id: str
    explanation: str


# ------------------------------------------------------------------------------ schemas


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            return _inline_refs(copy.deepcopy(defs[name]), defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def _close(node: Any) -> Any:
    if isinstance(node, dict):
        out = {k: _close(v) for k, v in node.items() if k not in ("default", "title")}
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out
    if isinstance(node, list):
        return [_close(v) for v in node]
    return node


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A closed JSON schema: refs inlined, every object closed, every property required."""
    raw = model.model_json_schema()
    inlined = _inline_refs(raw, raw.get("$defs", {}))
    closed = _close(inlined)
    assert isinstance(closed, dict)
    return closed


PARSE_REQUEST = ToolSpec(
    name="parse_request",
    description=(
        "Record the screening criteria the researcher's request states. Null means the "
        "request does not state it. List required items the request lacks in "
        "missing_required. Set out_of_scope when the request asks for something this "
        "assistant does not do."
    ),
    input_schema=strict_schema(ParsedRequest),
)
CLASSIFY_ABSTRACT = ToolSpec(
    name="classify_abstract",
    description=(
        "Classify one abstract into a fixed evidence label with the deposition method it "
        "states and one sentence copied exactly from the abstract that supports the label."
    ),
    input_schema=strict_schema(ClassifyAbstract),
)
WRITE_RATIONALE = ToolSpec(
    name="write_rationale",
    description=(
        "Fill the listed rationale slots with plain text. Numbers, formulas, ranks, and ids "
        "appear only as the template tokens given; never as literal digits."
    ),
    input_schema=strict_schema(WriteRationale),
)
PROPOSE_RELAXATION = ToolSpec(
    name="propose_relaxation",
    description=(
        "Pick one of the computed relaxations by its id and explain it in one plain sentence "
        "without digits. The researcher approves or declines; nothing is applied here."
    ),
    input_schema=strict_schema(ProposeRelaxation),
)

TOOLS: dict[str, tuple[ToolSpec, type[BaseModel]]] = {
    "parse_request": (PARSE_REQUEST, ParsedRequest),
    "classify_abstract": (CLASSIFY_ABSTRACT, ClassifyAbstract),
    "write_rationale": (WRITE_RATIONALE, WriteRationale),
    "propose_relaxation": (PROPOSE_RELAXATION, ProposeRelaxation),
}


class ToolInputError(ValueError):
    pass


def validate_input(name: str, raw: dict[str, Any]) -> BaseModel:
    """The model's tool input, validated against the tool's input model or rejected."""
    try:
        _, model = TOOLS[name]
    except KeyError:
        raise ToolInputError(f"unknown tool {name!r}") from None
    try:
        return model.model_validate(raw)
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
        )
        raise ToolInputError(f"invalid {name} input: {problems}") from None
