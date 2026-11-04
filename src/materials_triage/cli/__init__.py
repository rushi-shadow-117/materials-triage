"""Command-line interface.

Commands: query, rank, replay, diff, eval, export, serve (serve stays a stub for Track C).
Every run goes through the same pipeline; the CLI only parses, confirms, renders, and stores.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from materials_triage.agent import llm_status, pipeline, relaxation
from materials_triage.agent import parse as parse_mod
from materials_triage.agent.llm import LLMClient
from materials_triage.agent.loop import Budget
from materials_triage.agent.parse import ParseOutcome, resolve_outcome
from materials_triage.agent.scoring_port import ScorerUnavailableError
from materials_triage.config.schema import QuerySettings
from materials_triage.records.bundle import DecisionLogEntry, ProvenanceBundle
from materials_triage.render import csv_export, markdown
from materials_triage.settings import Settings

from . import confirm as confirm_mod
from . import rundiff as diff_mod
from . import wiring

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="materials-triage: triage candidate materials from public data.",
)

NOT_IMPLEMENTED = "not implemented (Track C)"
DEFAULT_PROFILE = "oxide_dielectric_thin_film"
EXIT_REFUSED = 0
EXIT_ABORTED = 1
EXIT_USAGE = 2
EXIT_FAILED = 3

ProfileOpt = Annotated[str, typer.Option(help="Scoring profile name")]
ViewOpt = Annotated[str, typer.Option(help="pi_summary | audit")]
FetchOpt = Annotated[
    str,
    typer.Option(
        "--fetch",
        help="auto (store if Postgres answers, else cassettes) | store (Postgres-backed, "
        "FETCH_MODE from .env) | cassettes (recorded, no database)",
    ),
]
NoLlmOpt = Annotated[
    bool,
    typer.Option("--no-llm", help="Parse from --criteria, skip classification, template rationale"),
]
ExportOpt = Annotated[str | None, typer.Option("--export", help="json | csv | md")]
OutOpt = Annotated[Path | None, typer.Option("--out", help="Write the export here")]


def _settings() -> Settings:
    try:
        return Settings()
    except Exception as e:  # noqa: BLE001 - settings errors are usage errors
        typer.echo(f"settings error: {e}", err=True)
        raise typer.Exit(code=EXIT_USAGE) from None


def _fail(message: str, code: int = EXIT_FAILED) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=code)


def _llm(settings: Settings, no_llm: bool) -> LLMClient | None:
    client = wiring.make_llm(settings, no_llm=no_llm)
    if client is None and not no_llm:
        if settings.llm_provider == "none":
            _fail("LLM_PROVIDER=none: pass --no-llm with --criteria", EXIT_USAGE)
        _fail(f"{llm_status.note()} Set the key in .env or pass --no-llm.", EXIT_USAGE)
    return client


def _run_and_render(
    *,
    settings: Settings,
    layers: wiring.Layers,
    outcome: ParseOutcome,
    request_text: str,
    client: LLMClient | None,
    fetch_source: str,
    view: str,
    export: str | None,
    out: Path | None,
    extra_log: list[DecisionLogEntry] | None = None,
    prior_budgets: list[Budget] | None = None,
) -> ProvenanceBundle:
    try:
        source, fetch_line = wiring.resolve_fetch_source(settings, fetch_source)
    except ValueError as e:
        _fail(str(e), EXIT_USAGE)
    typer.echo(fetch_line, err=True)
    fetch_note = DecisionLogEntry(
        at=datetime.now(UTC), actor="cli", step="fetch_source", summary=fetch_line
    )
    extra_log = [*(extra_log or []), fetch_note]
    inputs = pipeline.RunInputs(
        request_text=request_text,
        parse=outcome,
        core=layers.core,
        site=layers.site,
        profile=layers.profile,
        hazard_policy=layers.hazard_policy,
        confirmed_at=datetime.now(UTC),
        prior_budgets=list(prior_budgets or []),  # parse (and relax) spent before this run
    )
    fetch, mode = wiring.make_fetch(settings, source, run_id=inputs.run_id)
    inputs.fetch_mode = mode
    try:
        bundle = pipeline.run(
            inputs,
            fetch=fetch,
            sources=pipeline.Sources.load(),
            scorer=wiring.make_scorer(),
            llm=client,
            cache=wiring.make_cache(settings),
        )
    except ScorerUnavailableError as e:
        _fail(f"scoring unavailable: {e}")
    if extra_log:
        bundle = bundle.model_copy(update={"decision_log": [*extra_log, *bundle.decision_log]})
    path = wiring.make_run_store(settings).save(bundle)
    typer.echo(f"run {bundle.run.run_id} saved to {path}", err=True)
    if bundle.criteria.mode != "refused":
        typer.echo(_render(bundle, layers, view))
    _export(bundle, layers, export, out, view)
    return bundle


def _render(bundle: ProvenanceBundle, layers: wiring.Layers, view: str) -> str:
    try:
        return markdown.render(bundle, view=view, site=layers.site)
    except ValueError as e:
        _fail(str(e), EXIT_USAGE)


def _export(
    bundle: ProvenanceBundle, layers: wiring.Layers, fmt: str | None, out: Path | None, view: str
) -> None:
    if fmt is None:
        return
    text = _export_text(bundle, layers, fmt, view)
    if out is None:
        typer.echo(text)
    else:
        out.write_text(text)
        typer.echo(f"exported {fmt} to {out}", err=True)


def _export_text(bundle: ProvenanceBundle, layers: wiring.Layers, fmt: str, view: str) -> str:
    if fmt == "json":
        return bundle.model_dump_json(indent=1) + "\n"
    if fmt == "csv":
        units, _ = markdown.options_from_bundle(bundle, layers.site)
        return csv_export.export_csv(bundle, units=units)
    if fmt in ("md", "markdown"):
        return _render(bundle, layers, view)
    _fail("--export must be json, csv, or md", EXIT_USAGE)


def _maybe_relax(
    *,
    bundle: ProvenanceBundle,
    outcome: ParseOutcome,
    layers: wiring.Layers,
    client: LLMClient | None,
    request_text: str,
    yes: bool,
    budget: Budget,
) -> ParseOutcome | None:
    """When fewer than top_n ranked: offer one computed relaxation; apply only on approval.
    `budget` is the relax step's budget; the caller records what it used."""
    if client is None or outcome.query is None or outcome.effective is None:
        return None
    if len(bundle.ranked()) >= outcome.effective.top_n:
        return None
    choices = relaxation.relaxations_from_bundle(bundle)  # counted by the pipeline
    if not choices:
        return None
    result = relaxation.run_relax(
        client=client,
        choices=choices,
        request_text=request_text,
        budget=budget,
    )
    if result.choice is None:
        typer.echo(f"no relaxation proposed ({result.reason})", err=True)
        return None
    text = f"Relaxation proposed: {result.choice.describe()}. {result.explanation or ''}".strip()
    if yes:
        typer.echo(text + " (not applied: relaxations need an explicit answer)", err=True)
        return None
    if not confirm_mod.confirm(text, yes=False):
        typer.echo("relaxation declined", err=True)
        return None
    new_query = relaxation.apply_relaxation(outcome.query, result.choice)
    return resolve_outcome(
        new_query,
        parsed_by=outcome.parsed_by,
        core=layers.core,
        site=layers.site,
        profile=layers.profile,
        defaults=list(outcome.defaults_applied),
        missing=[],
    )


@app.command()
def query(
    request: Annotated[str, typer.Argument(help="Natural-language request from the PI")],
    profile: ProfileOpt = DEFAULT_PROFILE,
    yes: Annotated[
        bool, typer.Option("--yes", help="Skip the parsed-criteria confirmation")
    ] = False,
    no_llm: NoLlmOpt = False,
    criteria: Annotated[Path | None, typer.Option(help="Criteria file for --no-llm mode")] = None,
    view: ViewOpt = "pi_summary",
    export: ExportOpt = None,
    out: OutOpt = None,
    fetch: FetchOpt = "auto",
) -> None:
    """Parse a request, confirm criteria, run the pipeline, render a view."""
    settings = _settings()
    try:
        layers = wiring.load_layers(profile)
    except FileNotFoundError as e:
        _fail(str(e), EXIT_USAGE)
    client = _llm(settings, no_llm)
    spent: list[Budget] = []  # step budgets used before the run (parse, then relax)
    if no_llm:
        if criteria is None:
            _fail("--no-llm needs --criteria FILE", EXIT_USAGE)
        try:
            outcome = parse_mod.parse_from_file(
                criteria,
                core=layers.core,
                site=layers.site,
                profile=layers.profile,
                cli_profile=layers.profile.name,
            )
        except (ValueError, parse_mod.CandidateListError) as e:
            _fail(str(e), EXIT_USAGE)
    else:
        assert client is not None
        parse_budget = Budget.from_core(layers.core, "parse")
        spent.append(parse_budget)
        step = parse_mod.run_parse(
            client=client,
            request_text=request,
            core=layers.core,
            site=layers.site,
            profile=layers.profile,
            cli_profile=layers.profile.name,
            budget=parse_budget,
        )
        if not step.ok or step.outcome is None:
            _fail(f"could not parse the request: {step.reason}")
        outcome = step.outcome.data
    if outcome.refusal is not None:
        typer.echo(outcome.refusal)
        _run_and_render(
            settings=settings,
            layers=layers,
            outcome=outcome,
            request_text=request,
            client=client,
            fetch_source=fetch,
            view=view,
            export=None,
            out=None,
            prior_budgets=spent,
        )
        raise typer.Exit(code=EXIT_REFUSED)
    assert outcome.query is not None
    if outcome.missing_required:
        if yes:
            _fail("missing required: " + ", ".join(outcome.missing_required), EXIT_USAGE)
        typer.echo(confirm_mod.describe(outcome))
        filled = confirm_mod.fill_missing(
            outcome.query, outcome.missing_required, lambda q: str(typer.prompt(q))
        )
        outcome = resolve_outcome(
            filled,
            parsed_by=outcome.parsed_by,
            core=layers.core,
            site=layers.site,
            profile=layers.profile,
            defaults=list(outcome.defaults_applied),
            missing=[],
        )
    if not confirm_mod.confirm(confirm_mod.describe(outcome), yes=yes):
        typer.echo("aborted; nothing was run", err=True)
        raise typer.Exit(code=EXIT_ABORTED)
    bundle = _run_and_render(
        settings=settings,
        layers=layers,
        outcome=outcome,
        request_text=request,
        client=client,
        fetch_source=fetch,
        view=view,
        export=export,
        out=out,
        prior_budgets=spent,
    )
    relax_budget = Budget.from_core(layers.core, "relax")
    relaxed = _maybe_relax(
        bundle=bundle,
        outcome=outcome,
        layers=layers,
        client=client,
        request_text=request,
        yes=yes,
        budget=relax_budget,
    )
    if any(v for v in relax_budget.used().values()):
        # the relax step ran after this bundle was saved: add its budget and save again
        run = bundle.run.model_copy(
            update={
                "budgets_used": {**bundle.run.budgets_used, **relax_budget.used()},
                "budgets_limit": {**bundle.run.budgets_limit, **relax_budget.limits()},
            }
        )
        wiring.make_run_store(settings).save(bundle.model_copy(update={"run": run}))
        spent.append(relax_budget)
    if relaxed is not None:
        accepted = DecisionLogEntry(
            at=datetime.now(UTC),
            actor="user",
            step="relaxation_accepted",
            summary="relaxation approved on the terminal; new run",
            detail={"previous_run": str(bundle.run.run_id)},
        )
        _run_and_render(
            settings=settings,
            layers=layers,
            outcome=relaxed,
            request_text=request,
            client=client,
            fetch_source=fetch,
            view=view,
            export=export,
            out=out,
            extra_log=[accepted],
            prior_budgets=spent,
        )


@app.command()
def rank(
    formulas: Annotated[
        list[str],
        typer.Option("--formulas", help="Candidate formulas, comma separated or repeated"),
    ],
    profile: ProfileOpt = DEFAULT_PROFILE,
    view: ViewOpt = "pi_summary",
    no_llm: NoLlmOpt = False,
    export: ExportOpt = None,
    out: OutOpt = None,
    fetch: FetchOpt = "auto",
) -> None:
    """Rank a PI-supplied candidate list on the same criteria as discovery."""
    settings = _settings()
    try:
        layers = wiring.load_layers(profile)
    except FileNotFoundError as e:
        _fail(str(e), EXIT_USAGE)
    client = _llm(settings, no_llm)
    flat = [f.strip() for chunk in formulas for f in chunk.split(",") if f.strip()]
    try:
        candidates = parse_mod.normalize_candidates(flat, layers.profile.synonyms)
    except parse_mod.CandidateListError as e:
        _fail(str(e), EXIT_USAGE)
    outcome = resolve_outcome(
        QuerySettings(
            profile=layers.profile.name, mode="candidate_list", candidate_list=candidates
        ),
        parsed_by="form",
        core=layers.core,
        site=layers.site,
        profile=layers.profile,
        defaults=[],
        missing=[],
    )
    typer.echo(confirm_mod.describe(outcome), err=True)
    _run_and_render(
        settings=settings,
        layers=layers,
        outcome=outcome,
        request_text="rank " + ", ".join(candidates),
        client=client,
        fetch_source=fetch,
        view=view,
        export=export,
        out=out,
    )


@app.command()
def replay(
    run_id: Annotated[str, typer.Argument(help="Run id of a stored bundle")],
    view: ViewOpt = "pi_summary",
    fetch: FetchOpt = "cassettes",
) -> None:
    """Re-rank a stored run's criteria from stored data: no network, new run id."""
    settings = _settings()
    store = wiring.make_run_store(settings)
    try:
        previous = store.load(run_id)
    except FileNotFoundError as e:
        _fail(str(e), EXIT_USAGE)
    layers = wiring.load_layers(previous.run.profile_name)
    if fetch == "store" and settings.fetch_mode != "replay":
        _fail("replay with --fetch store needs FETCH_MODE=replay", EXIT_USAGE)
    try:
        query_settings = QuerySettings.model_validate(previous.criteria.effective_settings)
    except ValueError as e:
        _fail(f"stored criteria are not replayable: {e}", EXIT_USAGE)
    outcome = resolve_outcome(
        query_settings,
        parsed_by=previous.criteria.parsed_by,
        core=layers.core,
        site=layers.site,
        profile=layers.profile,
        defaults=list(previous.criteria.defaults_applied),
        missing=[],
    )
    note = DecisionLogEntry(
        at=datetime.now(UTC),
        actor="user",
        step="replay",
        summary=f"replay of run {previous.run.run_id} with no fetching",
        detail={"source_run": str(previous.run.run_id)},
    )
    _run_and_render(
        settings=settings,
        layers=layers,
        outcome=outcome,
        request_text=previous.criteria.request_text,
        client=None,
        fetch_source=fetch,
        view=view,
        export=None,
        out=None,
        extra_log=[note],
    )


@app.command()
def diff(run_a: str, run_b: str) -> None:
    """Attribute rank changes between two runs to data, config, or model."""
    settings = _settings()
    store = wiring.make_run_store(settings)
    try:
        a, b = store.load(run_a), store.load(run_b)
    except FileNotFoundError as e:
        _fail(str(e), EXIT_USAGE)
    typer.echo(diff_mod.to_markdown(diff_mod.diff(a, b)))


@app.command()
def eval(  # noqa: A001 - command name from the plan
    suite: Annotated[str, typer.Option(help="Eval suite or case id")] = "all",
) -> None:
    """Run the eval suite (Track E runner)."""
    try:
        from evals import runner  # type: ignore[import-not-found,import-untyped,unused-ignore]
    except ImportError:
        typer.echo("eval runner pending")
        raise typer.Exit(code=EXIT_USAGE) from None
    raise typer.Exit(code=int(runner.main(suite)))


@app.command()
def export(
    run_id: str,
    fmt: Annotated[str, typer.Option("--format", help="json | csv | markdown")] = "json",
    view: ViewOpt = "pi_summary",
    out: OutOpt = None,
) -> None:
    """Export a stored bundle."""
    settings = _settings()
    try:
        bundle = wiring.make_run_store(settings).load(run_id)
    except FileNotFoundError as e:
        _fail(str(e), EXIT_USAGE)
    layers = wiring.load_layers(bundle.run.profile_name)
    text = _export_text(bundle, layers, fmt, view)
    if out is None:
        typer.echo(text, nl=False)
    else:
        out.write_text(text)
        typer.echo(f"exported {fmt} to {out}", err=True)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    no_web: Annotated[
        bool, typer.Option("--no-web", help="API only; do not mount web/dist")
    ] = False,
) -> None:
    """Serve the API and, when web/dist exists, the web app, in one process."""
    import uvicorn

    from materials_triage.api.app import WEB_DIST, create_app
    from materials_triage.api.auth import AuthConfigError

    settings = _settings()
    try:
        application = create_app(settings, serve_web=not no_web)
    except AuthConfigError as e:
        _fail(str(e), EXIT_USAGE)
    dist = settings.web_dist or WEB_DIST
    web = f"with {dist}" if (not no_web and dist.exists()) else "API only"
    typer.echo(
        f"serving on http://{host}:{port} ({web}); auth {settings.auth_mode}, "
        f"llm {settings.llm_provider}, classify {settings.classify_mode}",
        err=True,
    )
    uvicorn.run(application, host=host, port=port, log_level="info")


def main() -> None:
    app()
