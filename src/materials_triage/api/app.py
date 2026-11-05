"""The HTTP API. Every route reads the caller's role from the bearer token (auth.py); runs go
through the same pipeline the CLI uses (runs.py); views are the render package's view models
serialized as JSON, so the browser never formats a number.

`create_app()` builds an app for one Settings object; the module-level `app` uses the
process settings and is what `materials-triage serve`, the OpenAPI export, and uvicorn load.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from materials_triage.agent import estimate as estimate_mod
from materials_triage.agent import llm_status, pipeline, relaxation
from materials_triage.agent import parse as parse_mod
from materials_triage.agent.loop import Budget
from materials_triage.cli import wiring
from materials_triage.config import limits
from materials_triage.config.schema import (
    CoreConfig,
    QuerySettings,
    covered_properties,
    resolve,
    unavailable_properties,
)
from materials_triage.records import record_url
from materials_triage.records.bundle import (
    Anchor,
    Candidate,
    DecisionLogEntry,
    ProvenanceBundle,
)
from materials_triage.render import csv_export, markdown
from materials_triage.render.caveats import CaveatConfig
from materials_triage.render.views import build
from materials_triage.scoring.band_gap import experimental_pool
from materials_triage.settings import Settings

from . import admin, auth
from . import help as help_mod
from .runs import RunManager
from .schemas import (
    CallEstimateOut,
    CoveredProperty,
    DrillResponse,
    DrillValue,
    HazardRow,
    HealthResponse,
    LayerRow,
    Me,
    ParseRequest,
    ParseResponse,
    ProfileSaved,
    ProfileSummary,
    ProfileValidation,
    RefreshAccepted,
    RefreshRequest,
    RelaxChoice,
    RelaxRequest,
    ResolveRequest,
    ResolveResponse,
    RunAccepted,
    RunRequest,
    RunSummary,
    UnresolvedOut,
    WeightBoundRow,
)

ROOT = Path(__file__).resolve().parents[3]
WEB_DIST = ROOT / "web" / "dist"
API_PREFIX = "/api"  # every API route; everything else is the web app or its files


def create_app(settings: Settings | None = None, *, serve_web: bool = False) -> FastAPI:
    settings = settings or Settings()
    auth.check_startup(settings)
    wiring.initial_llm_status(settings)
    app = FastAPI(
        title="materials-triage",
        version="0.1.0",
        description=(
            "Triage candidate materials from public data. Every number traces to a source "
            "record; roles come only from the bearer token."
        ),
        docs_url=f"{API_PREFIX}/docs",
        swagger_ui_oauth2_redirect_url=f"{API_PREFIX}/docs/oauth2-redirect",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.state.settings = settings
    app.state.audit = auth.AuditLog(settings.data_cache_dir / "audit.log")
    app.state.static_tokens = auth.parse_static_tokens(settings.static_tokens)
    if settings.auth_mode == "oidc":
        app.state.oidc = auth.OidcVerifier(
            settings.oidc_issuer or "", settings.oidc_audience or "", settings.oidc_roles_claim
        )
    app.state.runs = RunManager(settings, wiring.make_run_store(settings), pipeline.Sources.load())
    app.state.layers = {}
    router = APIRouter(prefix=API_PREFIX)
    _routes(router)
    app.include_router(router)
    dist = settings.web_dist or WEB_DIST
    if serve_web and dist.exists():
        app.mount("/", SpaStaticFiles(directory=dist, html=True), name="web")
    return app


class SpaStaticFiles(StaticFiles):
    """The built web app: a client-side route (no file extension) falls back to index.html so
    deep links and reloads such as /runs/<id> and /console load the app; real files are served
    as is. An unknown /api path stays a 404 and never becomes the app."""

    async def get_response(self, path: str, scope: Any) -> Any:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            is_api = path == API_PREFIX.strip("/") or path.startswith(API_PREFIX.strip("/") + "/")
            if e.status_code == 404 and not is_api and "." not in path.rsplit("/", 1)[-1]:
                return await super().get_response("index.html", scope)
            raise


# ----------------------------------------------------------------------------- helpers


def _layers(request: Request, profile_id: str) -> wiring.Layers:
    cache: dict[str, wiring.Layers] = request.app.state.layers
    if profile_id not in cache:
        try:
            admin.profile_path(profile_id)
            cache[profile_id] = wiring.load_layers(profile_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None
    return cache[profile_id]


def _limits(
    core: CoreConfig, *, request_text: str | None = None, settings: dict[str, Any] | None = None
) -> None:
    """Core input limits as a 422 with a sentence (config/limits.py)."""
    try:
        limits.check_request_limits(core, request_text=request_text, settings=settings)
    except limits.LimitExceededError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


def _bundle(request: Request, run_id: str) -> ProvenanceBundle:
    runs: RunManager = request.app.state.runs
    try:
        return runs.load_bundle(run_id)
    except FileNotFoundError:
        state = runs.get(run_id)
        if state is not None and not state.done.is_set():
            raise HTTPException(status_code=409, detail="run still in progress") from None
        if state is not None and state.status in ("cancelled", "failed"):
            raise HTTPException(
                status_code=410, detail=f"run {state.status}: {state.error or ''}"
            ) from None
        raise HTTPException(status_code=404, detail="run not found") from None


def _summary(request: Request, run_id: str, *, light: bool = False) -> RunSummary:
    """`light`: read the stored summary index instead of the bundle (the history list; a
    discovery bundle is tens of megabytes and the list took seconds)."""
    runs: RunManager = request.app.state.runs
    state = runs.get(run_id)

    def from_state() -> RunSummary:
        assert state is not None
        return RunSummary(
            run_id=run_id,
            status=state.status,
            profile=state.profile,
            request_text=state.request_text,
            started_at=state.started_at.isoformat(),
            finished_at=state.finished_at.isoformat() if state.finished_at else None,
            error=state.error,
        )

    if state is not None and not state.done.is_set():
        # in flight: answer from the state and never touch the run file, which the worker
        # may be writing at this moment (the save is atomic, but this costs nothing)
        return from_state()
    if light:
        try:
            d = runs.store.summary(run_id)
        except FileNotFoundError:
            if state is None:
                raise HTTPException(status_code=404, detail="run not found") from None
            return from_state()
        return RunSummary(
            run_id=run_id,
            status="refused" if d["mode"] == "refused" else "completed",
            profile=d["profile"],
            request_text=d["request_text"],
            started_at=d["started_at"],
            finished_at=d["finished_at"],
            partial=d["partial"],
            ranked=d["ranked"],
            excluded=d["excluded"],
        )
    try:
        b = runs.load_bundle(run_id)
    except FileNotFoundError:
        if state is None:
            raise HTTPException(status_code=404, detail="run not found") from None
        return from_state()
    return RunSummary(
        run_id=run_id,
        status="refused" if b.criteria.mode == "refused" else "completed",
        profile=b.run.profile_name,
        request_text=b.criteria.request_text,
        started_at=b.run.started_at.isoformat(),
        finished_at=b.run.finished_at.isoformat() if b.run.finished_at else None,
        partial=b.run.partial,
        ranked=len(b.ranked()),
        excluded=len(b.excluded()),
    )


def _outcome_response(outcome: parse_mod.ParseOutcome, *, model: str | None) -> ParseResponse:
    return ParseResponse(
        parse_available=True,
        parsed_by=outcome.parsed_by,
        refusal=outcome.refusal,
        refusal_category=outcome.category.value if outcome.category else None,
        settings=outcome.query.model_dump(mode="json") if outcome.query else None,
        clamps=list(outcome.clamps),
        defaults_applied=list(outcome.defaults_applied),
        missing_required=list(outcome.missing_required),
        unresolved_candidates=list(outcome.unresolved_candidates),
        unavailable_properties=list(outcome.unavailable_properties),
        requested_properties=list(outcome.requested_properties),
        covered_properties=[
            CoveredProperty(name=n, criterion=c)
            for n, c in covered_properties(outcome.requested_properties)
        ],
        model=model,
    )


def _row(bundle: ProvenanceBundle, composition: str) -> Candidate | Anchor:
    rows: list[Candidate | Anchor] = [*bundle.candidates, *bundle.anchors]
    for row in rows:
        if row.composition == composition:
            return row
    raise HTTPException(status_code=404, detail=f"{composition} is not a row of this run")


# ----------------------------------------------------------------------------- routes


def _routes(app: APIRouter) -> None:  # noqa: C901 - one function registers every route
    @app.get("/me", response_model=Me)
    def me(principal: auth.Current) -> Me:
        return Me(
            subject=principal.subject,
            role=principal.role,
            auth_mode=principal.mode,
            role_switch=principal.mode == "none",
            **llm_status.describe(),
        )

    @app.get("/profiles", response_model=list[ProfileSummary])
    def profiles(_: auth.AnyRole) -> list[ProfileSummary]:
        return admin.list_profiles()

    @app.post("/parse", response_model=ParseResponse)
    def parse_request(request: Request, body: ParseRequest, _: auth.AnyRole) -> ParseResponse:
        """Parse a free-text request with the configured model. With LLM_PROVIDER=none the
        confirm form is filled by hand (no call is made)."""
        settings: Settings = request.app.state.settings
        layers = _layers(request, body.profile)
        _limits(layers.core, request_text=body.request_text)
        client = wiring.make_llm(settings, no_llm=False)
        if client is None:
            return ParseResponse(parse_available=False, reason=llm_status.note())
        step = parse_mod.run_parse(
            client=client,
            request_text=body.request_text,
            core=layers.core,
            site=layers.site,
            profile=layers.profile,
            cli_profile=layers.profile.name,
            budget=Budget.from_core(layers.core, "parse"),
        )
        if step.reason == "llm_unavailable":
            return ParseResponse(parse_available=False, reason=llm_status.note())
        if not step.ok or step.outcome is None:
            return ParseResponse(
                parse_available=True, reason=f"parse failed: {step.reason}", model=client.model
            )
        return _outcome_response(step.outcome.data, model=client.model)

    @app.post("/criteria/resolve", response_model=ResolveResponse)
    def resolve_criteria(
        request: Request, body: ResolveRequest, _: auth.AnyRole
    ) -> ResolveResponse:
        """Pure: the confirm form's current values through the same clamps a run applies."""
        layers = _layers(request, body.profile)
        _limits(layers.core, settings=body.settings)
        try:
            outcome = parse_mod.parse_from_settings(
                body.settings,
                core=layers.core,
                site=layers.site,
                profile=layers.profile,
                cli_profile=layers.profile.name,
            )
        except (ValueError, parse_mod.CandidateListError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        assert outcome.query is not None and outcome.effective is not None
        settings: Settings = request.app.state.settings
        calls = estimate_mod.estimate(
            query=outcome.query,
            effective=outcome.effective,
            core=layers.core,
            classify_mode=settings.classify_mode,
        )
        return ResolveResponse(
            settings=outcome.query.model_dump(mode="json"),
            effective_weights=dict(outcome.effective.weights),
            stability_cutoff_mev=outcome.effective.stability_cutoff_mev,
            clamps=list(outcome.clamps),
            defaults_applied=list(outcome.defaults_applied),
            missing_required=list(outcome.missing_required),
            unresolved_candidates=list(outcome.unresolved_candidates),
            unresolved=[
                UnresolvedOut(text=t, reason=parse_mod.UNRESOLVED_REASON)
                for t in outcome.unresolved_candidates
            ],
            config_sha=outcome.effective.config_sha,
            estimated_model_calls=CallEstimateOut(**dataclasses.asdict(calls)),
        )

    @app.post("/runs", response_model=RunAccepted, status_code=202)
    def create_run(request: Request, body: RunRequest, principal: auth.AnyRole) -> RunAccepted:
        """Start a run from confirmed criteria. A request that names nothing to search on is
        answered 422 with the fields to supply; nothing is fetched."""
        layers = _layers(request, body.profile)
        _limits(layers.core, request_text=body.request_text, settings=body.settings)
        try:
            outcome = parse_mod.parse_from_settings(
                body.settings,
                core=layers.core,
                site=layers.site,
                profile=layers.profile,
                cli_profile=layers.profile.name,
                parsed_by=body.parsed_by,
            )
        except (ValueError, parse_mod.CandidateListError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        query = outcome.query
        assert query is not None
        if query.mode == "candidate_list" and not query.candidate_list:
            # nothing to rank: say why in a sentence, never a Python list
            raise HTTPException(
                status_code=422,
                detail=parse_mod.nothing_matched(outcome.unresolved_candidates)
                if outcome.unresolved_candidates
                else "Paste at least one formula or name to rank.",
            )
        unavailable = unavailable_properties(body.requested_properties)
        outcome = dataclasses.replace(outcome, unavailable_properties=unavailable)
        if query.mode == "discovery" and not body.requested_properties:
            # the confirm form states chemistry through the profile and properties through
            # settings; a form with neither is the clarification case
            has_setting = any(
                v not in (None, {}, [])
                for v in (
                    query.weights,
                    query.band_gap_min_ev,
                    query.band_gap_max_ev,
                    query.e_above_hull_max_mev,
                    query.max_elements,
                    query.evidence_tier_min,
                )
            )
            if not has_setting and not body.request_text.strip():
                raise HTTPException(
                    status_code=422,
                    detail={"missing_required": parse_mod.CLARIFY_FIELDS},
                )
        runs: RunManager = request.app.state.runs
        state = runs.start(
            outcome,
            layers,
            request_text=body.request_text or f"rank {', '.join(query.candidate_list)}",
            profile_id=body.profile,
            extra_log=[
                DecisionLogEntry(
                    at=state_time(),
                    actor="api",
                    step="confirmed",
                    summary=f"criteria confirmed by {principal.role} ({principal.mode})",
                )
            ],
        )
        return RunAccepted(run_id=str(state.run_id), status=state.status)

    @app.get("/runs", response_model=list[RunSummary])
    def list_runs(request: Request, _: auth.AnyRole, limit: int = 50) -> list[RunSummary]:
        runs: RunManager = request.app.state.runs
        ids = [p.stem for p in reversed(runs.store.list())]
        for rid, state in runs.states.items():
            if rid not in ids and not state.done.is_set():
                ids.insert(0, rid)
        return [_summary(request, rid, light=True) for rid in ids[:limit]]

    @app.get("/runs/{run_id}", response_model=ProvenanceBundle)
    def get_run(request: Request, run_id: str, _: auth.AnyRole) -> ProvenanceBundle:
        return _bundle(request, run_id)

    @app.get("/runs/{run_id}/status", response_model=RunSummary)
    def run_status(request: Request, run_id: str, _: auth.AnyRole) -> RunSummary:
        return _summary(request, run_id)

    @app.get("/runs/{run_id}/events")
    async def run_events(request: Request, run_id: str, _: auth.AnyRole) -> EventSourceResponse:
        """Server-sent events: one `step` per decision-log entry as it happens, then `done`."""
        runs: RunManager = request.app.state.runs
        if runs.get(run_id) is None:
            raise HTTPException(status_code=404, detail="no live run with that id")
        return EventSourceResponse(runs.stream(run_id))

    @app.post("/runs/{run_id}/cancel", response_model=RunSummary)
    def cancel_run(request: Request, run_id: str, _: auth.AnyRole) -> RunSummary:
        runs: RunManager = request.app.state.runs
        if not runs.cancel(run_id):
            raise HTTPException(status_code=409, detail="run is not in progress")
        return _summary(request, run_id)

    @app.get("/runs/{run_id}/view")
    def run_view(
        request: Request,
        run_id: str,
        _: auth.AnyRole,
        view: str = Query("pi_summary", pattern="^(pi_summary|audit)$"),
    ) -> JSONResponse:
        """The render package's view model as JSON: every value already formatted, units and
        terminology as the run was confirmed with. The PI view carries no record ids."""
        bundle = _bundle(request, run_id)
        layers = _layers(request, bundle.run.profile_name)
        units, _terminology = markdown.options_from_bundle(bundle, layers.site)
        hide_ids = view == "pi_summary"
        run_view = build(
            bundle,
            CaveatConfig.load(admin.profile_path(bundle.run.profile_name)),
            units=units,
            hide_ids=hide_ids,
        )
        data = jsonable_encoder(dataclasses.asdict(run_view))
        data["view"] = view
        data["run"] = jsonable_encoder(bundle.run)
        data["criteria"] = jsonable_encoder(bundle.criteria)
        data["verifier"] = jsonable_encoder(bundle.verifier)
        data["markdown"] = markdown.render(bundle, view=view, site=layers.site)
        if hide_ids:
            # the PI view: its columns only; the breakdown, polymorphs, quotes and records
            # are the audit view's and the drill-down's
            for key in ("rows", "excluded", "anchors"):
                data[key] = [{k: r[k] for k in PI_ROW_FIELDS if k in r} for r in data[key]]
            data["decision_log"] = []
        else:
            data["decision_log"] = jsonable_encoder(bundle.decision_log)
            data["relaxations"] = [c.model_dump() for c in _choices(bundle)]
        return JSONResponse(data)

    @app.get("/runs/{run_id}/export")
    def run_export(
        request: Request,
        run_id: str,
        _: auth.AnyRole,
        format: str = Query("json", pattern="^(json|csv|md)$"),
        view: str = Query("pi_summary", pattern="^(pi_summary|audit)$"),
    ) -> Any:
        bundle = _bundle(request, run_id)
        layers = _layers(request, bundle.run.profile_name)
        if format == "json":
            return JSONResponse(jsonable_encoder(bundle))
        units, _terminology = markdown.options_from_bundle(bundle, layers.site)
        if format == "csv":
            return PlainTextResponse(
                csv_export.export_csv(bundle, units=units), media_type="text/csv"
            )
        return PlainTextResponse(
            markdown.render(bundle, view=view, site=layers.site), media_type="text/markdown"
        )

    @app.get("/runs/{run_id}/drill/{composition}/{criterion}", response_model=DrillResponse)
    def drill(
        request: Request,
        run_id: str,
        composition: str,
        criterion: str,
        _: auth.AnyRole,
    ) -> DrillResponse:
        """Where one number came from: its record, method, fetch time, raw hash, the other
        values of the same property the run holds, and the rule that chose."""
        bundle = _bundle(request, run_id)
        layers = _layers(request, bundle.run.profile_name)
        return _drill(bundle, layers, _row(bundle, composition), criterion)

    @app.get("/runs/{run_id}/relaxations", response_model=list[RelaxChoice])
    def relaxations(request: Request, run_id: str, _: auth.AnyRole) -> list[RelaxChoice]:
        return _choices(_bundle(request, run_id))

    @app.post("/runs/{run_id}/relax", response_model=RunAccepted, status_code=202)
    def relax(
        request: Request,
        run_id: str,
        body: RelaxRequest,
        principal: auth.AnyRole,
    ) -> RunAccepted:
        """Apply one relaxation the pipeline computed and logged, as a new run. The
        researcher's click is the approval; nothing is applied without it."""
        bundle = _bundle(request, run_id)
        choice = next(
            (
                c
                for c in relaxation.relaxations_from_bundle(bundle)
                if c.choice_id == body.choice_id
            ),
            None,
        )
        if choice is None:
            raise HTTPException(
                status_code=404, detail=f"no relaxation {body.choice_id!r} on this run"
            )
        layers = _layers(request, bundle.run.profile_name)
        query = QuerySettings.model_validate(bundle.criteria.effective_settings)
        new_query = relaxation.apply_relaxation(query, choice)
        outcome = parse_mod.resolve_outcome(
            new_query,
            parsed_by="form",
            core=layers.core,
            site=layers.site,
            profile=layers.profile,
            defaults=list(bundle.criteria.defaults_applied),
            missing=[],
        )
        runs: RunManager = request.app.state.runs
        state = runs.start(
            outcome,
            layers,
            request_text=bundle.criteria.request_text,
            profile_id=bundle.run.profile_name,
            extra_log=[
                DecisionLogEntry(
                    at=state_time(),
                    actor="user",
                    step="relaxation_accepted",
                    summary=(
                        f"relaxation approved in the browser by {principal.role}: "
                        f"{choice.describe()}"
                    ),
                    detail={"previous_run": run_id, "choice_id": choice.choice_id},
                )
            ],
        )
        return RunAccepted(run_id=str(state.run_id), status=state.status)

    # ---------------------------------------------------------------- configuration

    @app.get("/config/effective")
    def effective_config(
        request: Request,
        _: auth.AnyRole,
        profile: str = "oxide_dielectric_thin_film",
    ) -> dict[str, Any]:
        layers = _layers(request, profile)
        eff, clamps = resolve(
            layers.core, layers.site, layers.profile, QuerySettings(profile=layers.profile.name)
        )
        return {
            "profile": profile,
            "effective": eff.model_dump(mode="json"),
            "clamps": [c.model_dump() for c in clamps],
            "notes": layers.notes,
        }

    @app.get("/config/layers", response_model=list[LayerRow])
    def config_layers(
        request: Request,
        _: auth.ConsoleRole,
        profile: str = "oxide_dielectric_thin_film",
    ) -> list[LayerRow]:
        return admin.layer_rows(_layers(request, profile))

    @app.get("/hazard-policy", response_model=list[HazardRow])
    def hazard_policy(_: auth.ConsoleRole) -> list[HazardRow]:
        return admin.hazard_rows(admin.hazard_policy())

    @app.get("/weight-bounds", response_model=list[WeightBoundRow])
    def weight_bounds(
        request: Request,
        _: auth.AnyRole,
        profile: str = "oxide_dielectric_thin_film",
    ) -> list[WeightBoundRow]:
        layers = _layers(request, profile)
        return admin.weight_bound_rows(layers.site, layers.profile)

    @app.post("/admin/profiles/validate", response_model=ProfileValidation)
    def validate_profile(
        request: Request,
        _: auth.ConsoleRole,
        body: str = Body(..., media_type="application/yaml"),
    ) -> ProfileValidation:
        layers = _layers(request, "oxide_dielectric_thin_film")
        return admin.validate_profile_yaml(body, layers.site)

    @app.post("/admin/profiles", response_model=ProfileSaved, status_code=201)
    def save_profile(
        request: Request,
        principal: auth.ConsoleRole,
        body: str = Body(..., media_type="application/yaml"),
    ) -> ProfileSaved:
        layers = _layers(request, "oxide_dielectric_thin_film")
        validation = admin.validate_profile_yaml(body, layers.site)
        try:
            saved = admin.save_profile_yaml(body, validation)
        except (ValueError, FileExistsError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        request.app.state.audit.write(
            "profile_saved",
            principal,
            file=saved.file,
            profile=saved.profile,
            version=saved.version,
        )
        request.app.state.layers.pop(saved.id, None)
        return saved

    @app.post("/admin/refresh", response_model=RefreshAccepted, status_code=202)
    def admin_refresh(
        request: Request, body: RefreshRequest, principal: auth.AdminRole
    ) -> RefreshAccepted:
        """Mark a source for refetch on the next store-backed run. Earlier runs keep their
        snapshot and hashes. The note is required and audit-logged."""
        if not admin.valid_source(body.source):
            raise HTTPException(status_code=422, detail=f"unknown source {body.source!r}")
        runs: RunManager = request.app.state.runs
        runs.pending_refresh.add(body.source)
        entry = request.app.state.audit.write(
            "refresh_requested", principal, source=body.source, note=body.note
        )
        return RefreshAccepted(
            status="accepted",
            source=body.source,
            applies_to="the next run that uses the Postgres store",
            audit_entry=entry,
        )

    @app.get("/audit", response_model=list[dict[str, Any]])
    def audit_log(request: Request, _: auth.AdminRole, limit: int = 200) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = request.app.state.audit.entries()
        return entries[-limit:]

    @app.get("/help/keys")
    def help_keys(_: auth.AnyRole) -> dict[str, list[str]]:
        """The closed vocabularies the in-app help text covers (web/src/help.ts)."""
        return help_mod.keys()

    @app.get("/help/{guide}", response_class=PlainTextResponse)
    def help_guide(guide: str, _: auth.AnyRole) -> PlainTextResponse:
        """A role guide as Markdown, from a fixed allowlist of two files under docs/."""
        text = help_mod.guide_text(guide)
        if text is None:
            raise HTTPException(
                status_code=404, detail=f"no guide named {guide!r}; use scientist or admin"
            )
        return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")

    @app.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        settings: Settings = request.app.state.settings
        fetch_source, _line = wiring.resolve_fetch_source(settings, "auto")
        return HealthResponse(
            status="ok",
            fetch_source=fetch_source,
            fetch_mode=settings.fetch_mode,
            **llm_status.describe(),
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model if settings.llm_provider != "none" else None,
            classify_mode=settings.classify_mode,
            auth_mode=settings.auth_mode,
            sources=admin.source_health(settings, fetch_source),
        )


# ----------------------------------------------------------------------------- view helpers


def state_time() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)


def _choices(bundle: ProvenanceBundle) -> list[RelaxChoice]:
    return [
        RelaxChoice(
            choice_id=c.choice_id,
            setting=c.setting,
            current=c.current,
            proposed=c.proposed,
            adds=c.adds,
            admits=list(c.admits),
            text=c.describe(),
        )
        for c in relaxation.relaxations_from_bundle(bundle)
    ]


PI_ROW_FIELDS = (
    "composition",
    "is_anchor",
    "rank",
    "tied",
    "total",
    "rationale",
    "rationale_verified",
    "key_caveat",
    "caveats",
    "flags",
    "evidence_tier",
    "k",
    "missing",
    "exclusion",
    "exclusion_detail",
    "exclusion_ref",
    "echa_attribution",
    "gaps",
    "band_gap_source",
)


def _drill(
    bundle: ProvenanceBundle, layers: wiring.Layers, row: Candidate | Anchor, criterion: str
) -> DrillResponse:
    from materials_triage.render import precision
    from materials_triage.scoring.profile import load_scoring_profile

    score = next(
        (s for s in (row.score.criteria if row.score else []) if s.criterion == criterion), None
    )
    if score is None:
        raise HTTPException(status_code=404, detail=f"{criterion} is not a scored criterion")
    units, _terminology = markdown.options_from_bundle(bundle, layers.site)
    p = score.provenance
    loaded = load_scoring_profile(admin.profile_path(bundle.run.profile_name))
    others: list[DrillValue] = []
    polys = row.group.polymorphs
    scored = polys.scored
    if criterion == "band_gap" and scored is not None:
        for method, value in sorted(scored.band_gap.items()):
            if value.value is not None:
                others.append(
                    DrillValue(
                        method=method,
                        value=precision.fmt(value.value, value.unit, units),
                        source=value.provenance.source,
                        record_id=value.provenance.source_record_id,
                        url=record_url(value.provenance),
                        used=(
                            p is not None
                            and value.provenance.source_record_id == p.source_record_id
                            and value.provenance.raw_sha256 == p.raw_sha256
                        ),
                    )
                )
        # every experimental value with its form; used only if it entered this row's score
        used_ids = set(score.used_record_ids)
        pool = experimental_pool(
            row.group.experimental_gaps,
            row.group.reference_values,
            loaded.profile.band_gap.preferred_forms,
        )
        for e in pool.entries:
            shown = (
                precision.fmt(e.value, "eV", units)
                if e.value is not None
                else f"{precision.fmt(e.low, 'eV', units)} to {precision.fmt(e.high, 'eV', units)}"
            )
            others.append(
                DrillValue(
                    method=f"experimental ({e.label})",
                    value=shown,
                    source=e.provenance.source,
                    record_id=e.provenance.source_record_id,
                    url=record_url(e.provenance),
                    used=e.provenance.source_record_id in used_ids,
                    form=e.form,
                )
            )
    elif criterion == "stability":
        for prow in polys.top_by_hull:
            if prow.hull_energy is not None and prow.hull_energy.value is not None:
                others.append(
                    DrillValue(
                        method=f"{prow.hull_energy.method} ({prow.mp_id})",
                        value=precision.fmt(prow.hull_energy.value, prow.hull_energy.unit, units),
                        source=prow.hull_energy.provenance.source,
                        record_id=prow.mp_id,
                        url=record_url(prow.hull_energy.provenance),
                        used=scored is not None and prow.mp_id == scored.mp_id,
                    )
                )
    elif criterion == "hazard" and row.group.hazard is not None:
        h = row.group.hazard
        others.append(
            DrillValue(
                method="GHS codes",
                value=", ".join(sorted(h.h_codes)) or "none",
                source=h.provenance.source,
                record_id=h.provenance.source_record_id,
                url=record_url(h.provenance),
                used=True,
            )
        )
    return DrillResponse(
        composition=row.composition,
        criterion=criterion,
        label=criterion.replace("_", " "),
        raw="missing"
        if score.raw_value is None
        else precision.fmt(score.raw_value, score.raw_unit, units),
        normalized="missing"
        if score.normalized is None
        else precision.fmt(score.normalized, "score"),
        weight=precision.fmt(score.weight, "score"),
        contribution=precision.fmt(score.contribution, "score"),
        missing_reason=score.missing_reason,
        # Source names the database (expt_gap, materials_project); Method names how the scored
        # value was taken from it (experimental_median). Both read "experimental_median" before.
        source=p.source if p else None,
        record_id=p.source_record_id if p else None,
        method=score.source,
        fetched_at=p.fetched_at.isoformat() if p else None,
        raw_sha256=p.raw_sha256 if p else None,
        source_version=p.source_version if p else None,
        source_url=record_url(p) if p else None,
        rule_ref=loaded.source_refs.get(criterion),
        notes=list(score.notes),
        other_values=others,
    )


def __getattr__(name: str) -> Any:
    """`app` is built on first use, not at import: importing this module (as `serve` does)
    must not run the startup checks before the caller can report their errors."""
    if name == "app":
        built = create_app()
        globals()["app"] = built
        return built
    raise AttributeError(name)


def openapi_schema() -> dict[str, Any]:
    return create_app().openapi()
