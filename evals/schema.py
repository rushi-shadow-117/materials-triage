"""Case files, observations, and results for the eval harness.

A Case is one query from internal/test-queries.md with its expectation verbatim and the
coded checks that decide it. An Observation is what one run produced: the bundle, the
transcript, the configuration before and after, the rendered views. Results carry every check
with its detail so the report can show why a case passed or failed.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from materials_triage.records.bundle import ProvenanceBundle


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# OWASP Top 10 for LLM Applications, 2025 edition. Ids are the vocabulary; a case names one.
OWASP_LLM_TOP10_2025: dict[str, str] = {
    "LLM01": "Prompt Injection",
    "LLM02": "Sensitive Information Disclosure",
    "LLM03": "Supply Chain",
    "LLM04": "Data and Model Poisoning",
    "LLM05": "Improper Output Handling",
    "LLM06": "Excessive Agency",
    "LLM07": "System Prompt Leakage",
    "LLM08": "Vector and Embedding Weaknesses",
    "LLM09": "Misinformation",
    "LLM10": "Unbounded Consumption",
}

JudgeItem = Literal["caveat_presence", "pi_summary_level"]


class OwaspTag(Strict):
    id: str  # LLM01 .. LLM10
    name: str

    @model_validator(mode="after")
    def _known(self) -> OwaspTag:
        expected = OWASP_LLM_TOP10_2025.get(self.id)
        if expected is None or expected != self.name:
            raise ValueError(f"unknown OWASP LLM Top 10 (2025) tag {self.id}: {self.name}")
        return self


class CheckSpec(Strict):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class Case(Strict):
    id: str  # e.g. A1, F1, G1
    group: str  # the letter
    kind: Literal["normal", "adversarial"]
    title: str
    request: str  # the query, verbatim
    expectation: str  # verbatim from internal/test-queries.md
    mode: Literal["discovery", "candidate_list"] = "discovery"
    candidate_list: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)  # QuerySettings overrides
    repeats: int = 1
    owasp: OwaspTag | None = None
    checks: list[CheckSpec] = Field(default_factory=list)  # every one must pass
    task_completion: list[CheckSpec] = Field(default_factory=list)  # F: all must pass
    defenses: list[CheckSpec] = Field(default_factory=list)  # F: attack succeeds if any fails
    judge: list[JudgeItem] = Field(default_factory=list)
    injected_fixture: str | None = None  # e.g. fixtures/synthetic/openalex_injection.json
    injected_into: str | None = None  # composition whose literature search serves the fixture
    profile: str | None = None  # scoring profile name (the CLI's choice); default profile if None
    llm: Literal["fake", "live", "none"] | None = None  # per-case override of the executor's mode
    fake_parse: dict[str, Any] | None = None  # what the scripted model answers for parse_request
    skip_reason: str | None = None  # set when the harness cannot run the case; reported as such

    @model_validator(mode="after")
    def _adversarial_rules(self) -> Case:
        if self.group == "F" and self.kind != "adversarial":
            raise ValueError(f"{self.id}: group F cases are adversarial")
        if self.kind == "adversarial" and self.owasp is None:
            raise ValueError(f"{self.id}: an adversarial case needs an OWASP tag")
        if self.kind == "adversarial" and not self.defenses:
            raise ValueError(f"{self.id}: an adversarial case needs defenses checks")
        if self.repeats < 1:
            raise ValueError(f"{self.id}: repeats must be at least 1")
        return self


class Message(Strict):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class Observation(Strict):
    """Everything a check may look at. Nothing here is computed by the harness."""

    case_id: str
    repeat: int
    run_id: str
    executor: str
    bundle: ProvenanceBundle | None
    transcript: list[Message] = Field(default_factory=list)
    rendered: dict[str, str] = Field(default_factory=dict)  # view name -> text
    config_sha_before: str
    config_sha_after: str
    config_files_before: dict[str, str] = Field(default_factory=dict)  # path -> sha256
    config_files_after: dict[str, str] = Field(default_factory=dict)
    log_entries: list[str] = Field(default_factory=list)  # harness or agent log lines
    llm_calls: int = 0
    errors: list[str] = Field(default_factory=list)


class CheckResult(Strict):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)
    passed: bool
    detail: str


class JudgeVerdict(Strict):
    item: JudgeItem
    verdict: Literal["pass", "fail", "judge_declined"]
    reason: str
    judge: str  # fake | model id


class RepeatResult(Strict):
    repeat: int
    run_id: str
    passed: bool
    checks: list[CheckResult]
    task_completed: bool | None = None  # adversarial only
    attack_succeeded: bool | None = None  # adversarial only
    judge: list[JudgeVerdict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class CaseResult(Strict):
    case_id: str
    group: str
    kind: str
    title: str
    expectation: str
    owasp: OwaspTag | None
    repeats: list[RepeatResult]
    pass_rate: float | None  # None when the case was skipped
    task_completion_rate: float | None
    attack_success_rate: float | None
    run_ids: list[str]
    repeats_identical: bool | None = None  # ranks, exclusions, prompt hash equal across repeats
    skipped: str | None = None  # the case file's skip_reason when it was not run


class SuiteResult(Strict):
    suite: str
    executor: str
    judge: str
    cases: list[CaseResult]
    passed_cases: int
    total_cases: int
    git_commit: str | None
    config_sha: str
    preregistration: dict[str, Any] | None = None
