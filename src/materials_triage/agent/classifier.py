"""Evidence classification: one abstract, one bounded conversation, one fixed label.

Code decides before the model is asked: a hit with no abstract is `no_abstract`; a
fulltext-scope hit is `computed_only` and never verified; without an LLM every hit is
`unclassified`. Results are cached by (abstract sha256, classify-step prompt hash, model
version) as JSON files, so a re-run with the same prompt and model never pays twice.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from materials_triage.records import LiteratureHit
from materials_triage.records.bundle import DecisionLogEntry, EvidenceHit, EvidenceLabel
from materials_triage.verify.quotes import check_quote
from materials_triage.verify.verifier import FULLTEXT_NOTE

from . import loop, prompts
from .llm import LLMClient
from .tools import CLASSIFY_ABSTRACT, ClassifyAbstract

QUOTE_ERROR = (
    "supporting_sentence is not a verbatim substring of the abstract: {note}. Copy one "
    "sentence exactly as it appears, or set it to null with not_relevant or no_abstract."
)


def abstract_sha(hit: LiteratureHit) -> str:
    if hit.abstract_index_sha256:
        return hit.abstract_index_sha256
    return hashlib.sha256((hit.abstract_text or "").encode()).hexdigest()


def cache_key(abstract_sha256: str, prompt_hash: str, model_version: str) -> str:
    return hashlib.sha256(f"{abstract_sha256}|{prompt_hash}|{model_version}".encode()).hexdigest()


class ClassifierCache:
    """JSON files under <data_cache_dir>/classifier/<key>.json."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def get(self, key: str) -> dict[str, Any] | None:
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{key}.json").write_text(json.dumps(value, sort_keys=True, indent=1))


@dataclass
class ClassifyResult:
    hits: list[EvidenceHit] = field(default_factory=list)
    entries: list[DecisionLogEntry] = field(default_factory=list)
    partial_reasons: list[str] = field(default_factory=list)
    llm_calls: int = 0
    cache_hits: int = 0


def _hit(
    composition: str,
    lit: LiteratureHit,
    *,
    label: EvidenceLabel,
    deposition_method: str | None,
    sentence: str | None,
    verified: bool,
    note: str | None,
    key: str | None,
) -> EvidenceHit:
    return EvidenceHit(
        composition=composition,
        openalex_id=lit.openalex_id,
        label=label,
        deposition_method=deposition_method,
        supporting_sentence=sentence,
        verified=verified,
        verifier_note=note,
        quote_verifiable=lit.quote_verifiable,
        classifier_cache_key=key,
        provenance=lit.provenance,
    )


def precheck(composition: str, lit: LiteratureHit) -> EvidenceHit | None:
    """The cases code settles without a model call."""
    if not lit.quote_verifiable:
        return _hit(
            composition,
            lit,
            label=EvidenceLabel.COMPUTED_ONLY,
            deposition_method=None,
            sentence=None,
            verified=False,
            note=FULLTEXT_NOTE,
            key=None,
        )
    if lit.abstract_text is None or not lit.abstract_text.strip():
        return _hit(
            composition,
            lit,
            label=EvidenceLabel.NO_ABSTRACT,
            deposition_method=None,
            sentence=None,
            verified=False,
            note=None,
            key=None,
        )
    return None


def unclassified(composition: str, lit: LiteratureHit, note: str | None = None) -> EvidenceHit:
    return _hit(
        composition,
        lit,
        label=EvidenceLabel.UNCLASSIFIED,
        deposition_method=None,
        sentence=None,
        verified=False,
        note=note,
        key=None,
    )


def make_handler(abstract_text: str) -> loop.Handler:
    def handler(parsed: BaseModel) -> loop.ToolOutcome:
        assert isinstance(parsed, ClassifyAbstract)
        needs_sentence = parsed.label not in (
            parsed.label.NOT_RELEVANT,
            parsed.label.NO_ABSTRACT,
        )
        if needs_sentence or parsed.supporting_sentence is not None:
            result = check_quote(parsed.supporting_sentence, abstract_text)
            if not result.ok:
                return loop.ToolOutcome(QUOTE_ERROR.format(note=result.note), is_error=True)
        return loop.ToolOutcome(
            "recorded",
            data=parsed,
            log_detail={
                "label": parsed.label.value,
                "deposition_method": parsed.deposition_method.value,
                "sentence_chars": len(parsed.supporting_sentence or ""),
            },
        )

    return handler


def classify_hits(
    *,
    client: LLMClient | None,
    hits: list[tuple[str, LiteratureHit]],
    budget: loop.Budget,
    cache: ClassifierCache | None,
    model_version: str | None,
) -> ClassifyResult:
    """Classify every (composition, hit) in order. Budget breach leaves the rest unclassified."""
    out = ClassifyResult()
    prompt_hash = prompts.step_hash("classify")
    system = prompts.system_prompt("classify")
    exhausted: str | None = None
    for composition, lit in hits:
        settled = precheck(composition, lit)
        if settled is not None:
            out.hits.append(settled)
            continue
        if client is None or model_version is None:
            out.hits.append(unclassified(composition, lit))
            continue
        if exhausted is not None:
            out.hits.append(unclassified(composition, lit, f"budget: {exhausted}"))
            continue
        assert lit.abstract_text is not None
        key = cache_key(abstract_sha(lit), prompt_hash, model_version)
        cached = cache.get(key) if cache is not None else None
        if cached is not None:
            out.cache_hits += 1
            out.hits.append(
                _hit(
                    composition,
                    lit,
                    label=EvidenceLabel(cached["label"]),
                    deposition_method=cached.get("deposition_method"),
                    sentence=cached.get("supporting_sentence"),
                    verified=bool(cached.get("verified", False)),
                    note=None,
                    key=key,
                )
            )
            continue
        result = loop.run_step(
            client=client,
            step="classify",
            system=system,
            user_text=prompts.data_block(lit.abstract_text),
            tool=CLASSIFY_ABSTRACT,
            handler=make_handler(lit.abstract_text),
            budget=budget,
        )
        out.entries.extend(result.entries)
        out.llm_calls += 1
        if result.status == loop.StepStatus.BUDGET:
            exhausted = result.reason or "budget"
            out.partial_reasons.append(f"classification stopped at {lit.openalex_id}: {exhausted}")
            out.hits.append(unclassified(composition, lit, f"budget: {exhausted}"))
            continue
        if not result.ok or not isinstance(result.tool_input, ClassifyAbstract):
            out.hits.append(unclassified(composition, lit, f"classifier failed: {result.reason}"))
            continue
        parsed = result.tool_input
        label = EvidenceLabel(parsed.label.value)
        method = (
            None if parsed.deposition_method.value == "unknown" else parsed.deposition_method.value
        )
        verified = parsed.supporting_sentence is not None
        record = {
            "label": label.value,
            "deposition_method": method,
            "supporting_sentence": parsed.supporting_sentence,
            "verified": verified,
            "model_version": model_version,
            "prompt_hash": prompt_hash,
        }
        if cache is not None:
            cache.put(key, record)
        out.hits.append(
            _hit(
                composition,
                lit,
                label=label,
                deposition_method=method,
                sentence=parsed.supporting_sentence,
                verified=verified,
                note=None,
                key=key,
            )
        )
    return out
