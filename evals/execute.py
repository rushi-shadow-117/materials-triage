"""Executors turn a Case into an Observation.

PipelineExecutor runs Track B's fixed pipeline: parse (the model, or the case file in no-LLM
mode), fetch from recorded data with no network (cassettes, or the seeded store in replay
mode), score with Track A's scorer, classify and write rationale with the model, verify,
render. The model is `CaseScriptedLLM` in CI (`--llm fake`), the configured provider with
`--llm live`, or absent with `--llm none`. An injected OpenAlex fixture replaces the search
response for one composition. No classifier cache, so every repeat classifies anew.

SampleBundleExecutor is the pre-merge path kept for the harness's own tests: normal cases
observe fixtures/bundles/sample_bundle.json and adversarial cases get a transcript from the
request-only fake.

Configuration is hashed before and after every run from the effective config and the files
under config/, so `config_unchanged` has something real to compare.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from evals.fake_llm import FakeLLM
from evals.pipeline_llm import CaseScriptedLLM
from evals.schema import Case, Message, Observation
from materials_triage.adapters import openalex
from materials_triage.adapters.base import Call, RawResponse
from materials_triage.agent import parse as parse_mod
from materials_triage.agent import pipeline, relaxation
from materials_triage.agent.llm import LLMClient, make_client
from materials_triage.agent.loop import Budget
from materials_triage.cli import wiring
from materials_triage.config.schema import (
    CONFIG_DIR,
    CoreConfig,
    QuerySettings,
    default_paths,
    resolve,
    scoring_profile_from_yaml,
    site_profile_from_yaml,
)
from materials_triage.records.bundle import FetchMode, ProvenanceBundle
from materials_triage.render import csv_export, markdown
from materials_triage.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_BUNDLE = ROOT / "fixtures" / "bundles" / "sample_bundle.json"
DEFAULT_RUN_DIR = ROOT / ".data-cache" / "evals" / "runs"
VIEWS = ("pi_summary", "audit")
INJECTION_TIME = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)

LlmMode = Literal["fake", "live", "none"]
FetchSource = Literal["cassettes", "store"]


class Executor(Protocol):
    name: str

    def run(self, case: Case, repeat: int) -> Observation: ...


def config_files_sha(config_dir: Path = CONFIG_DIR) -> dict[str, str]:
    return {
        str(p.relative_to(config_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(config_dir.rglob("*.yaml"))
    }


def effective_config_sha(case: Case | None = None) -> str:
    paths = default_paths()
    profile, _ = scoring_profile_from_yaml(paths["scoring_profile"])
    site = site_profile_from_yaml(paths["site_profile"])
    settings = {} if case is None else dict(case.settings)
    query = QuerySettings(profile=profile.name, **settings)
    effective, _ = resolve(CoreConfig(), site, profile, query)
    return effective.config_sha


def _sample_bundle() -> ProvenanceBundle:
    return ProvenanceBundle.model_validate_json(SAMPLE_BUNDLE.read_text())


class SampleBundleExecutor:
    name = "sample_bundle"

    def __init__(self, llm: FakeLLM | None = None) -> None:
        self.llm = llm or FakeLLM()

    def run(self, case: Case, repeat: int) -> Observation:
        before_sha, before_files = effective_config_sha(case), config_files_sha()
        transcript = [Message(role="user", content=case.request)]
        log: list[str] = []
        bundle: ProvenanceBundle | None = None
        reply = self.llm.respond(case.request)
        transcript.append(Message(role="assistant", content=reply))
        log.extend(self.llm.log[-1:])
        refused = self.llm.refusal_for(case.request) is not None
        if not refused:
            bundle = _sample_bundle()
            log.append(f"pipeline: sample bundle {bundle.run.run_id} served for {case.id}")
        else:
            log.append(f"refusal: {case.id} redirected by core policy; no run started")
        run_id = str(bundle.run.run_id) if bundle is not None else f"refused-{case.id}-{repeat}"
        after_sha, after_files = effective_config_sha(case), config_files_sha()
        return Observation(
            case_id=case.id,
            repeat=repeat,
            run_id=run_id,
            executor=self.name,
            bundle=bundle,
            transcript=transcript,
            rendered={},
            config_sha_before=before_sha,
            config_sha_after=after_sha,
            config_files_before=before_files,
            config_files_after=after_files,
            log_entries=log,
            llm_calls=1,
        )


# ----------------------------------------------------------------------------- the pipeline


def injected_fetch(
    base: pipeline.Fetch, *, fixture: Path, composition: str
) -> tuple[pipeline.Fetch, Call]:
    """Serve the synthetic OpenAlex works response for one composition's literature search;
    everything else comes from the base fetch."""
    call = openalex.plan_search(f"{composition} thin film")
    raw = RawResponse(
        call=call,
        status=200,
        body=fixture.read_bytes(),
        content_type="application/json",
        fetched_at=INJECTION_TIME,
    )

    def fetch(c: Call) -> RawResponse | None:
        return raw if c.cache_key == call.cache_key else base(c)

    return fetch, call


class ParseFailureError(Exception):
    pass


class ClarificationError(Exception):
    """The parse step asked for required fields the request and the case file do not give.
    That is an outcome, not an error: no run starts."""

    def __init__(self, fields: list[str]) -> None:
        super().__init__(", ".join(fields))
        self.fields = list(fields)


class PipelineExecutor:
    def __init__(
        self,
        *,
        llm: LlmMode = "fake",
        fetch_source: FetchSource = "cassettes",
        profile: str | None = None,
        run_dir: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.llm_mode: LlmMode = llm
        self.fetch_source: FetchSource = fetch_source
        self.name = f"pipeline:{llm}:{fetch_source}"
        self.default_profile = profile or default_paths()["scoring_profile"].stem
        self._layers: dict[str, wiring.Layers] = {}
        self.layers = self.layers_for_profile(self.default_profile)
        self.sources = pipeline.Sources.load()
        self.run_dir = run_dir or DEFAULT_RUN_DIR
        self._settings = settings
        self._cassettes: wiring.CassetteFetch | None = None
        self._live: LLMClient | None = None

    # -- pieces

    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = Settings()
        return self._settings

    def layers_for_profile(self, name: str) -> wiring.Layers:
        if name not in self._layers:
            self._layers[name] = wiring.load_layers(name)
        return self._layers[name]

    def layers_for(self, case: Case) -> wiring.Layers:
        return self.layers_for_profile(case.profile or self.default_profile)

    def llm_mode_for(self, case: Case) -> LlmMode:
        return case.llm or self.llm_mode

    def client(self, case: Case) -> LLMClient | None:
        mode = self.llm_mode_for(case)
        if mode == "none":
            return None
        if mode == "fake":
            return CaseScriptedLLM(case)
        if self._live is None:
            self._live = make_client(self.settings())
            if self._live is None:
                raise ValueError("--llm live needs LLM_PROVIDER set to a provider, not none")
        return self._live

    def fetch_for(self, case: Case, run_id: Any) -> tuple[pipeline.Fetch, FetchMode, list[str]]:
        log: list[str] = []
        base: pipeline.Fetch
        if self.fetch_source == "cassettes":
            if self._cassettes is None:
                self._cassettes = wiring.CassetteFetch()
            base, mode = self._cassettes, FetchMode.REPLAY
        else:
            settings = self.settings()
            if settings.fetch_mode != "replay":
                raise ValueError("--fetch store needs FETCH_MODE=replay (no network in evals)")
            base, mode = wiring.make_fetch(settings, "store", run_id=run_id)
        if case.injected_fixture is None:
            return base, mode, log
        fixture = ROOT / case.injected_fixture
        composition = case.injected_into or (
            parse_mod.normalize_candidates(case.candidate_list)[0] if case.candidate_list else ""
        )
        if not composition:
            raise ValueError(f"{case.id}: injected_fixture needs injected_into or a candidate list")
        fetch, call = injected_fetch(base, fixture=fixture, composition=composition)
        log.append(
            f"harness: injected {case.injected_fixture} as the OpenAlex response for "
            f"{composition} ({call.endpoint} {call.cache_key[:12]})"
        )
        return fetch, mode, log

    def parse(
        self, case: Case, client: LLMClient | None
    ) -> tuple[parse_mod.ParseOutcome, list[str]]:
        layers = self.layers_for(case)
        core, site, profile = layers.core, layers.site, layers.profile
        log: list[str] = []
        if client is None:
            query = QuerySettings(
                profile=profile.name,
                mode=case.mode,
                candidate_list=parse_mod.normalize_candidates(case.candidate_list),
                **case.settings,
            )
            outcome = parse_mod.resolve_outcome(
                query,
                parsed_by="criteria_file",
                core=core,
                site=site,
                profile=profile,
                defaults=[],
                missing=[],
            )
            log.append("harness: criteria taken from the case file (no LLM parse)")
        else:
            step = parse_mod.run_parse(
                client=client,
                request_text=case.request,
                core=core,
                site=site,
                profile=profile,
                cli_profile=profile.name,
                budget=Budget.from_core(core),
            )
            if not step.ok or step.outcome is None:
                raise ParseFailureError(f"parse failed: {step.reason}")
            outcome = step.outcome.data
            log.append(
                "harness: parsed by the model; "
                + (
                    f"refused ({outcome.category.value if outcome.category else 'policy'})"
                    if outcome.refusal is not None
                    else f"mode {outcome.query.mode if outcome.query else '?'}"
                )
            )
        if outcome.refusal is None and outcome.missing_required:
            assert outcome.query is not None
            updates: dict[str, Any] = {}
            for key in outcome.missing_required:
                if key == "candidate_list" and case.candidate_list:
                    updates[key] = parse_mod.normalize_candidates(case.candidate_list)
                elif key in case.settings:
                    updates[key] = case.settings[key]
            still = [k for k in outcome.missing_required if k not in updates]
            if still:
                raise ClarificationError(still)
            outcome = parse_mod.resolve_outcome(
                outcome.query.model_copy(update=updates),
                parsed_by=outcome.parsed_by,
                core=core,
                site=site,
                profile=profile,
                defaults=list(outcome.defaults_applied),
                missing=[],
            )
            log.append(
                "harness: filled missing_required from the case file, as the terminal "
                "confirmation would: " + ", ".join(sorted(updates))
            )
        if outcome.refusal is None and outcome.missing_required:
            raise ParseFailureError("missing required: " + ", ".join(outcome.missing_required))
        return outcome, log

    # -- the run

    def run(self, case: Case, repeat: int) -> Observation:
        before_sha, before_files = effective_config_sha(case), config_files_sha()
        transcript = [Message(role="user", content=case.request)]
        log: list[str] = []
        errors: list[str] = []
        bundle: ProvenanceBundle | None = None
        rendered: dict[str, str] = {}
        llm_calls = 0
        run_id = f"error-{case.id}-{repeat}"
        client = self.client(case)
        layers = self.layers_for(case)
        try:
            outcome, parse_log = self.parse(case, client)
            log.extend(parse_log)
            inputs = pipeline.RunInputs(
                request_text=case.request,
                parse=outcome,
                core=layers.core,
                site=layers.site,
                profile=layers.profile,
                hazard_policy=layers.hazard_policy,
                confirmed_at=datetime.now(UTC),
            )
            fetch, mode, fetch_log = self.fetch_for(case, inputs.run_id)
            inputs.fetch_mode = mode
            log.extend(fetch_log)
            bundle = pipeline.run(
                inputs,
                fetch=fetch,
                sources=self.sources,
                scorer=wiring.make_scorer(),
                llm=client,
                cache=None,
            )
            run_id = str(bundle.run.run_id)
            log.append(
                f"pipeline: run {run_id} from {self.fetch_source} in {mode.value} mode, "
                f"llm {self.llm_mode}; {len(bundle.candidates)} candidates, "
                f"mode {bundle.criteria.mode}"
            )
            if bundle.criteria.mode == "refused":
                refused = next((d for d in bundle.decision_log if d.step == "refused"), None)
                text = str(refused.detail.get("text", refused.summary)) if refused else ""
                transcript.append(Message(role="assistant", content=text))
                log.append(f"refusal: {case.id} ended at parse; nothing fetched")
            for view in VIEWS:
                try:
                    rendered[view] = markdown.render(bundle, view=view, site=layers.site)
                except Exception as e:  # noqa: BLE001 - a render failure is an observed error
                    errors.append(f"render {view}: {type(e).__name__}: {e}")
            if bundle.criteria.mode != "refused":
                transcript.append(Message(role="assistant", content=rendered.get("pi_summary", "")))
                try:
                    units, _ = markdown.options_from_bundle(bundle, layers.site)
                    rendered["csv"] = csv_export.export_csv(bundle, units=units)
                except Exception as e:  # noqa: BLE001 - observed, not raised
                    errors.append(f"export csv: {type(e).__name__}: {e}")
                if outcome.query is not None:
                    choices = relaxation.enumerate_relaxations(bundle, outcome.query)
                    log.append(
                        f"harness: relaxations available (code, not applied): {len(choices)}"
                        + ("; " + "; ".join(c.describe() for c in choices) if choices else "")
                    )
            self._save(bundle)
        except ClarificationError as e:
            run_id = f"clarification-{case.id}-{repeat}"
            log.append(f"harness: the parse asked for: {e}; no run started")
            transcript.append(Message(role="assistant", content=f"Please provide: {e}"))
        except ParseFailureError as e:
            errors.append(str(e))
            log.append(f"harness: {e}")
        if isinstance(client, CaseScriptedLLM):
            llm_calls = len(client.requests)
        elif bundle is not None:
            llm_calls = int(
                sum(v for k, v in bundle.run.budgets_used.items() if k.endswith("requests"))
                or bundle.run.budgets_used.get("tool_calls", 0)
            )
        after_sha, after_files = effective_config_sha(case), config_files_sha()
        return Observation(
            case_id=case.id,
            repeat=repeat,
            run_id=run_id,
            executor=self.name,
            bundle=bundle,
            transcript=transcript,
            rendered=rendered,
            config_sha_before=before_sha,
            config_sha_after=after_sha,
            config_files_before=before_files,
            config_files_after=after_files,
            log_entries=log,
            llm_calls=llm_calls,
            errors=errors,
        )

    def _save(self, bundle: ProvenanceBundle) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        path = self.run_dir / f"{bundle.run.run_id}.json"
        path.write_text(bundle.model_dump_json(indent=1) + "\n")
        return path


def observation_to_json(obs: Observation) -> str:
    return json.dumps(obs.model_dump(mode="json"), sort_keys=True)
