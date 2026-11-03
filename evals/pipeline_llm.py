"""A scripted stand-in for the model inside Track B's agent loop, for CI runs of the cases.

It implements Track B's `LLMClient` protocol and answers from the offered tool and the case:

- parse_request: a request the harness's refusal triggers match becomes the matching
  out-of-scope category; anything else becomes the case file's mode, candidate list and
  settings, so the parse step is exercised but never guesses.
- classify_abstract: a label chosen by keywords in the data block, with a supporting sentence
  copied verbatim from the abstract, so the classifier's quote check sees real input. A planted
  instruction in an abstract is data to this fake like any other sentence.
- write_rationale: token-only text for every slot the data block lists. No digits, ever.

Same case, same answers, no network. The live model replaces it with `--llm live`.
"""

from __future__ import annotations

import re
from typing import Any

from evals.fake_llm import TRIGGERS
from evals.schema import Case
from materials_triage.agent.llm import LLMResponse, Request, ToolCall, ToolSpec, Turn, Usage
from materials_triage.agent.prompts import FRAGMENTS
from materials_triage.agent.rationale import OVERVIEW

DATA_PREFIX, DATA_SUFFIX = FRAGMENTS["user.data"].split("{data}")

PARSE_KEYS = (
    "top_n",
    "band_gap_min_ev",
    "band_gap_max_ev",
    "max_elements",
    "evidence_tier_min",
    "exclude_radioactive",
    "verbosity",
    "terminology",
    "units",
    "view",
)

# (keyword in the lowercased abstract, label). First match wins.
LABEL_KEYWORDS: list[tuple[str, str]] = [
    ("dielectric", "dielectric_characterized"),
    ("film", "thin_film_deposited"),
    ("synthes", "bulk_synthesized"),
    ("calculat", "computed_only"),
    ("first-principles", "computed_only"),
    ("density functional", "computed_only"),
]
METHOD_KEYWORDS: list[tuple[str, str]] = [
    ("atomic layer deposition", "ALD"),
    ("ald", "ALD"),
    ("sputter", "sputtering"),
    ("pulsed laser", "PLD"),
    ("chemical vapor", "CVD"),
    ("sol-gel", "sol_gel"),
    ("sol gel", "sol_gel"),
    ("evaporat", "evaporation"),
]


def refusal_category(request: str) -> str | None:
    text = request.lower()
    for pattern, policy in TRIGGERS:
        if re.search(pattern, text):
            return policy
    return None


def data_block_text(turns: list[Turn]) -> str | None:
    """The DATA block of the latest user turn, or None when the turn carries none."""
    for turn in reversed(turns):
        if turn.role != "user" or turn.text is None:
            continue
        if turn.text.startswith(DATA_PREFIX) and turn.text.endswith(DATA_SUFFIX):
            return turn.text[len(DATA_PREFIX) : len(turn.text) - len(DATA_SUFFIX)]
    return None


def sentences(text: str) -> list[str]:
    """Contiguous slices of the text, so each one is a verbatim substring."""
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def classify_input(abstract: str) -> dict[str, Any]:
    lower = abstract.lower()
    label = "not_relevant"
    parts = sentences(abstract)
    # Always quote a sentence: the verifier checks a quote on every label except no_abstract
    # and unclassified, so a not_relevant hit without one is dropped as a quote mismatch.
    sentence: str | None = parts[0] if parts else None
    for keyword, candidate in LABEL_KEYWORDS:
        if keyword in lower:
            label = candidate
            sentence = next((s for s in parts if keyword in s.lower()), sentence)
            break
    method = "unknown"
    for keyword, candidate in METHOD_KEYWORDS:
        if keyword in lower:
            method = candidate
            break
    return {"label": label, "deposition_method": method, "supporting_sentence": sentence}


def rationale_input(data: str) -> dict[str, Any]:
    first = data.splitlines()[0] if data else ""
    slots = [s.strip() for s in first.removeprefix("slots to fill:").split(",") if s.strip()]
    out = []
    for slot in slots:
        bits = slot.split(":")
        if slot == OVERVIEW:
            text = (
                "Ranked candidates are listed with their caveats; "
                "missing values are shown as missing."
            )
        elif len(bits) == 3 and bits[0] == "candidate":
            text = f"{{formula:{bits[1]}}} ranks {{rank:{bits[1]}}}; see its caveats."
        else:
            continue
        out.append({"slot": slot, "text": text})
    return {"slots": out}


class CaseScriptedLLM:
    """Track B's LLMClient, answering for one case. Records every request like Track B's fake."""

    provider = "fake"

    def __init__(self, case: Case, *, model: str = "fake-model") -> None:
        self.case = case
        self.model = model
        self.requests: list[Request] = []

    def parse_input(self) -> dict[str, Any]:
        if self.case.fake_parse is not None:
            return dict(self.case.fake_parse)
        category = refusal_category(self.case.request)
        if category is not None:
            return {"out_of_scope": category}
        out: dict[str, Any] = {"mode": self.case.mode}
        if self.case.candidate_list:
            out["candidate_list"] = list(self.case.candidate_list)
        for key in PARSE_KEYS:
            if key in self.case.settings:
                out[key] = self.case.settings[key]
        if "weights" in self.case.settings:
            out["weights"] = dict(self.case.settings["weights"])
        return out

    def complete(
        self, *, system: str, turns: list[Turn], tools: list[ToolSpec], max_tokens: int
    ) -> LLMResponse:
        self.requests.append(Request(system, tuple(turns), tuple(tools), max_tokens))
        offered = tools[0].name if tools else None
        data = data_block_text(turns)
        payload: dict[str, Any] | None = None
        if offered == "parse_request":
            payload = self.parse_input()
        elif offered == "classify_abstract" and data is not None:
            payload = classify_input(data)
        elif offered == "write_rationale" and data is not None:
            payload = rationale_input(data)
        usage = Usage(input_tokens=100, output_tokens=20)
        if payload is None or offered is None:
            return LLMResponse(
                text="", tool_calls=(), stop_reason="end_turn", usage=usage, model=self.model
            )
        call = ToolCall(id=f"fake_{len(self.requests)}", name=offered, input=payload)
        return LLMResponse(
            text="", tool_calls=(call,), stop_reason="tool_use", usage=usage, model=self.model
        )
