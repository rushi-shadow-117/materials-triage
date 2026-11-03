"""The fixed pipeline: fetch, group, score, classify, write rationale, verify, assemble.

Data collection is not an agent decision: every composition gets the same cross-checks. The
pipeline is pure over an injected fetch function (the store-backed Runner in production, a
cassette transport in tests) and an injected scorer (Track A's, or the sample stand-in until
it merges). The LLM steps run only when a client is given; without one the run is identical
except for `unclassified` evidence and template-only rationale.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml

from materials_triage.adapters import expt_gap, jarvis, mp, openalex, pubchem
from materials_triage.adapters.base import Call, NotFetchedError, RawResponse
from materials_triage.adapters.common import reduced_formula
from materials_triage.config.schema import (
    CoreConfig,
    EffectiveConfig,
    QuerySettings,
    ScoringProfile,
    SiteProfile,
    default_paths,
)
from materials_triage.records import (
    CompositionGroup,
    ExperimentalGapAggregate,
    LiteratureHit,
    LiteratureSearchResult,
    Polymorph,
    SourceRecord,
)
from materials_triage.records.bundle import (
    Clamp,
    ConfirmedCriteria,
    DecisionLogEntry,
    EvidenceHit,
    FetchMode,
    MissingPropertyMarker,
    ProvenanceBundle,
    RationaleSlot,
    RunMetadata,
)
from materials_triage.records.groups import build_group, merge_matches
from materials_triage.verify.verifier import verify

from . import classifier, prompts, rationale
from .llm import LLMClient
from .loop import Budget
from .parse import ParseOutcome
from .scoring_port import ScoredSet, Scorer, ScoreRequest

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOTS = ROOT / "fixtures" / "snapshots"
COMPOSITIONS = ROOT / "fixtures" / "compositions.yaml"

Fetch = Callable[[Call], RawResponse | None]


# ----------------------------------------------------------------------------- fetching


class FetchContext:
    """Wraps a fetch function and collects availability events for calls it could not serve."""

    def __init__(self, fetch: Fetch) -> None:
        self._fetch = fetch
        self.events: list[dict[str, Any]] = []

    def get(self, call: Call) -> RawResponse | None:
        raw = self._fetch(call)
        if raw is None:
            self.events.append(
                {
                    "source": call.source.value,
                    "endpoint": call.endpoint,
                    "params": dict(call.params),
                    "at": datetime.now(UTC).isoformat(),
                    "error": "not available",
                }
            )
            return None
        return raw


@dataclass
class Sources:
    """Snapshot-backed sources, loaded once per process."""

    jarvis_polymorphs: list[Polymorph]
    gap_aggregates: dict[str, ExperimentalGapAggregate]
    versions: dict[str, str]
    names: dict[str, str]  # reduced formula -> common name for PubChem

    @classmethod
    def load(cls, snapshots: Path = SNAPSHOTS, compositions: Path = COMPOSITIONS) -> Sources:
        manifest = json.loads((snapshots / "MANIFEST.json").read_text())["snapshots"]
        fixed = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
        jv_raw = jarvis.load_slice(
            snapshots / "jarvis_dft_3d.slice.json",
            full_file_sha256=manifest["jarvis_dft_3d"]["sha256"],
            fetched_at=fixed,
        )
        gap_raw = expt_gap.load_slice(
            snapshots / "expt_gap.slice.json",
            table="expt_gap",
            file_sha256=manifest["expt_gap"]["sha256"],
            fetched_at=fixed,
        )
        names: dict[str, str] = {}
        if compositions.exists():
            spec = yaml.safe_load(compositions.read_text())
            for display, name in (spec.get("common_names") or {}).items():
                names[reduced_formula(display)] = str(name)
        return cls(
            jarvis_polymorphs=jarvis.polymorphs(jarvis.records(jv_raw)),
            gap_aggregates=expt_gap.aggregates(expt_gap.records(gap_raw)[0]),
            versions={
                "jarvis_dft_3d": manifest["jarvis_dft_3d"]["sha256"][:12],
                "expt_gap": manifest["expt_gap"]["sha256"][:12],
            },
            names=names,
        )


def fetch_composition(
    key: str, *, ctx: FetchContext, sources: Sources, synonyms: dict[str, list[str]]
) -> CompositionGroup | None:
    """The same cross-checks for every composition. Missing sources stay missing."""
    summary_raw = ctx.get(mp.plan_summary_by_formula(key))
    if summary_raw is None:
        return None
    summary = mp.summary_records(summary_raw)
    ids = [s.source_record_id for s in summary]
    thermo = []
    diel = []
    for call in mp.plan_thermo(ids):
        raw = ctx.get(call)
        if raw is not None:
            thermo.extend(mp.thermo_records(raw))
    for call in mp.plan_dielectric(ids):
        raw = ctx.get(call)
        if raw is not None:
            diel.extend(mp.dielectric_records(raw))
    polys = mp.assemble(summary, thermo, diel).polymorphs
    merged = merge_matches(polys, [p for p in sources.jarvis_polymorphs if p.composition == key])

    hazard = None
    name = sources.names.get(key) or (synonyms.get(key) or [key])[0]
    by_name = ctx.get(pubchem.plan_cids_by_name(name))
    by_formula = ctx.get(pubchem.plan_cids_by_formula(key))
    if by_name is not None and by_formula is not None:
        cid, _ = pubchem.choose_cid(pubchem.cids(by_name), pubchem.cids(by_formula))
        ghs = ctx.get(pubchem.plan_ghs(cid)) if cid else None
        syn = ctx.get(pubchem.plan_synonyms(cid)) if cid else None
        hazard = pubchem.hazard(key, by_name=by_name, by_formula=by_formula, ghs=ghs, syn=syn)

    literature: LiteratureSearchResult | None = None
    query = f"{key} thin film"
    search = ctx.get(openalex.plan_search(query))
    if search is not None:
        count = ctx.get(openalex.plan_count(query))
        literature = openalex.result(
            search, count, composition=key, query=query, scope="title_and_abstract"
        )
    return build_group(
        key,
        merged,
        experimental_gaps=sources.gap_aggregates.get(key),
        hazard=hazard,
        literature=literature,
    )


# ----------------------------------------------------------------------------- the run


@dataclass
class RunInputs:
    request_text: str
    parse: ParseOutcome
    core: CoreConfig
    site: SiteProfile
    profile: ScoringProfile
    hazard_policy: dict[str, Any]
    confirmed_at: datetime | None = None
    fetch_mode: FetchMode = FetchMode.REPLAY
    run_id: UUID = field(default_factory=uuid4)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    prior_budgets: list[Budget] = field(default_factory=list)  # e.g. the CLI's parse step


def code_version() -> str:
    try:
        return version("materials-triage")
    except PackageNotFoundError:
        return "unknown"


def policy_version(path: Path | None = None) -> str:
    """Short content hash of the hazard policy file, so a policy edit changes the run."""
    return sha256((path or default_paths()["hazard_policy"]).read_bytes()).hexdigest()[:12]


def _log(step: str, summary: str, actor: str = "pipeline", **detail: Any) -> DecisionLogEntry:
    return DecisionLogEntry(
        at=datetime.now(UTC), actor=actor, step=step, summary=summary, detail=detail
    )


def missing_markers(site: SiteProfile) -> list[MissingPropertyMarker]:
    return [
        MissingPropertyMarker(
            property=item.lower().replace(" ", "_"),
            text=item,
            source_entry="config/site_profile.default.yaml#screen_cannot_tell_you",
        )
        for item in site.screen_cannot_tell_you
    ]


def refusal_bundle(inputs: RunInputs, effective: EffectiveConfig | None) -> ProvenanceBundle:
    """A bundle with no candidates that carries the refusal in its decision log."""
    outcome = inputs.parse
    text = outcome.refusal or inputs.core.refusals.config_change
    log = [
        _log("start", "run started", code_version=code_version()),
        _log(
            "refused",
            text,
            category=outcome.category.value if outcome.category else None,
            text=text,
        ),
    ]
    return ProvenanceBundle(
        run=_run_metadata(inputs, effective, prompt_hash=None, model=None, provider=None),
        criteria=ConfirmedCriteria(
            request_text=inputs.request_text,
            parsed_by=outcome.parsed_by,
            confirmed_at=None,
            mode="refused",
            effective_settings={},
        ),
        candidates=[],
        decision_log=log,
    )


def _run_metadata(
    inputs: RunInputs,
    effective: EffectiveConfig | None,
    *,
    prompt_hash: str | None,
    model: str | None,
    provider: str | None,
    source_versions: dict[str, str] | None = None,
    partial_reasons: list[str] | None = None,
    budgets: list[Budget] | None = None,
    note: str | None = None,
    finished: bool = False,
) -> RunMetadata:
    used: dict[str, float] = {}
    limits: dict[str, float] = {}
    for b in budgets or []:
        used.update(b.used())
        limits.update(b.limits())
    return RunMetadata(
        run_id=inputs.run_id,
        started_at=inputs.started_at,
        finished_at=datetime.now(UTC) if finished else None,
        config_sha=effective.config_sha if effective else "",
        profile_name=inputs.profile.name,
        profile_version=inputs.profile.version,
        policy_version=policy_version(),
        prompt_hash=prompt_hash,
        model_version=model,
        provider=provider,
        source_versions=source_versions or {},
        fetch_mode=inputs.fetch_mode,
        partial=bool(partial_reasons),
        partial_reasons=list(partial_reasons or []),
        budgets_used=used,
        budgets_limit=limits,
        note=note,
    )


def discovery_filter(query: QuerySettings, profile: ScoringProfile) -> mp.DiscoveryFilter:
    """The MP query for discovery mode. The stability cutoff is a scoring rule shown as an
    exclusion, so it is never folded into the API filter. A discovery query needs a gap
    floor (every oxide is above the ceiling): the query's, else the profile's hard minimum,
    else its soft preference start; the gap ceiling is the query's, else the profile's."""
    policy = profile.simplicity.anion_policy
    elements: tuple[str, ...] = (
        ("O",) if policy == "strict_oxide" else ("N",) if policy == "strict_nitride" else ()
    )
    exclude: tuple[str, ...] = ()
    if policy == "strict_nitride":
        exclude = ("O", "F", "Cl", "Br", "I", "S", "Se", "Te", "P", "As", "Sb", "H")
    gap = profile.band_gap
    floor = query.band_gap_min_ev
    if floor is None:
        floor = gap.hard_min_ev if gap.hard_min_ev is not None else gap.soft_preference_start_ev
    ceiling = query.band_gap_max_ev if query.band_gap_max_ev is not None else gap.hard_max_ev
    return mp.DiscoveryFilter(
        elements=elements or ("O",),
        nelements_min=2,
        nelements_max=query.max_elements or profile.simplicity.max_elements,
        band_gap_min=floor,
        band_gap_max=ceiling,
        exclude_elements=exclude,
    )


@dataclass
class Collected:
    groups: dict[str, CompositionGroup]
    partial: list[str]
    log: list[DecisionLogEntry]
    refused: str | None = None  # discovery above the ceiling


def collect_candidate_list(
    keys: list[str], *, ctx: FetchContext, sources: Sources, synonyms: dict[str, list[str]]
) -> Collected:
    out = Collected({}, [], [])
    for key in keys:
        group = fetch_composition(key, ctx=ctx, sources=sources, synonyms=synonyms)
        if group is None:
            out.partial.append(f"{key}: no Materials Project summary available")
            continue
        out.groups[key] = group
    out.log.append(
        _log(
            "fetch",
            f"fetched {len(out.groups)} of {len(keys)} compositions",
            events=len(ctx.events),
        )
    )
    return out


def summary_groups(records: list[SourceRecord], sources: Sources) -> dict[str, CompositionGroup]:
    """Groups from summary records alone (pass 1 of discovery): hull and gap from the summary
    document, experimental gaps from the snapshot, no hazard or literature yet."""
    polys_by_comp: dict[str, list[Polymorph]] = {}
    for poly in mp.assemble(records).polymorphs:
        polys_by_comp.setdefault(poly.composition, []).append(poly)
    return {
        comp: build_group(comp, polys, experimental_gaps=sources.gap_aggregates.get(comp))
        for comp, polys in sorted(polys_by_comp.items())
    }


def collect_discovery(
    query: QuerySettings,
    *,
    profile: ScoringProfile,
    ctx: FetchContext,
    sources: Sources,
) -> Collected:
    """Discovery: page every match or refuse above the ceiling, then build summary-level
    groups. Enrichment happens in the run loop, which repeats until the final top K is
    enriched (an exclusion found by enrichment admits the next candidate)."""
    out = Collected({}, [], [])
    f = discovery_filter(query, profile)

    def fetch(call: Call) -> RawResponse:
        raw = ctx.get(call)
        if raw is None:
            raise NotFetchedError(call)
        return raw

    try:
        result = mp.run_discovery(fetch, f, ceiling=mp.DISCOVERY_CEILING)
    except NotFetchedError as e:
        out.partial.append(f"discovery: {e}")
        out.log.append(_log("discovery", "discovery query not available", params=f.params()))
        return out
    if result.refused:
        out.refused = (
            f"discovery matched {result.total_available} documents, above the ceiling of "
            f"{result.ceiling}; narrow the query"
        )
        out.log.append(
            _log("discovery", out.refused, total=result.total_available, ceiling=result.ceiling)
        )
        return out
    out.groups = summary_groups(result.records, sources)
    out.log.append(
        _log(
            "discovery",
            f"{result.returned} summary documents in {len(out.groups)} compositions",
            params=f.params(),
            total=result.total_available,
        )
    )
    return out


MAX_ENRICHMENT_ROUNDS = 12  # each round enriches only newcomers to the top K
MAX_ENRICHED_PER_TOP = 5  # stop once 5 x top_n compositions have been enriched


def run(
    inputs: RunInputs,
    *,
    fetch: Fetch,
    sources: Sources,
    scorer: Scorer,
    llm: LLMClient | None = None,
    cache: classifier.ClassifierCache | None = None,
) -> ProvenanceBundle:
    outcome = inputs.parse
    if outcome.refusal is not None:
        return refusal_bundle(inputs, outcome.effective)
    if outcome.query is None or outcome.effective is None:
        raise ValueError("the run needs resolved criteria")
    query, effective = outcome.query, outcome.effective

    budgets = {step: Budget.from_core(inputs.core, step) for step in ("classify", "rationale")}
    all_budgets = [*inputs.prior_budgets, *budgets.values()]
    log: list[DecisionLogEntry] = [
        _log("start", "run started", code_version=code_version(), mode=query.mode)
    ]
    partial: list[str] = []
    ctx = FetchContext(fetch)

    # 1. the MP database version, then fetch (the same cross-checks for every composition)
    mp_version: str | None = None
    heartbeat = ctx.get(mp.plan_heartbeat())
    if heartbeat is not None:
        mp_version = mp.parse_heartbeat(heartbeat)
    else:
        partial.append("materials_project: database version not available")

    def score_groups(
        groups: dict[str, CompositionGroup],
        evidence: dict[str, list[EvidenceHit]] | None = None,
    ) -> ScoredSet:
        return scorer(
            ScoreRequest(
                groups=groups,
                effective=effective,
                profile=inputs.profile,
                hazard_policy=inputs.hazard_policy,
                evidence=evidence or {},
                top_k=effective.top_n,
            )
        )

    enriched: set[str] = set()  # compositions the full cross-checks were attempted for
    if query.mode == "candidate_list":
        keys = list(dict.fromkeys([*query.candidate_list, *inputs.profile.anchors]))
        collected = collect_candidate_list(
            keys, ctx=ctx, sources=sources, synonyms=inputs.profile.synonyms
        )
        enriched.update(keys)
    else:
        collected = collect_discovery(query, profile=inputs.profile, ctx=ctx, sources=sources)
    log.extend(collected.log)
    partial.extend(collected.partial)
    if collected.refused is not None:
        partial.append(collected.refused)
    groups = collected.groups

    # 2. score, enrich the ranked top K (plus anchors) that are not yet enriched, classify
    #    their hits, score again with the evidence; repeat while enrichment changes the top K
    model = llm.model if llm is not None else None
    provider = llm.provider if llm is not None else None
    cap = inputs.core.max_abstracts_per_candidate
    evidence_by_comp: dict[str, list[EvidenceHit]] = {}
    all_hits: list[EvidenceHit] = []
    llm_calls = cache_hits = 0
    scored = score_groups(groups, evidence_by_comp) if groups else ScoredSet([], [])
    classified_keys: set[str] = set()
    for round_no in range(1, MAX_ENRICHMENT_ROUNDS + 1):
        ranked = sorted(
            (c for c in scored.candidates if c.rank is not None), key=lambda c: c.rank or 0
        )
        top = [c.composition for c in ranked[: effective.top_n]]
        need_enrich = [
            k for k in [*top, *inputs.profile.anchors] if k in groups and k not in enriched
        ]
        need_classify = [k for k in top if k in groups and k not in classified_keys]
        if not need_enrich and not need_classify:
            break
        if (
            len(enriched) >= MAX_ENRICHED_PER_TOP * effective.top_n
            and query.mode != "candidate_list"
        ):
            partial.append(
                f"enrichment stopped after {len(enriched)} compositions; "
                f"{', '.join(need_enrich)} in the top {effective.top_n} lack cross-checks"
            )
            break
        if need_enrich:
            fetched = 0
            for key in need_enrich:
                enriched.add(key)
                full = fetch_composition(
                    key, ctx=ctx, sources=sources, synonyms=inputs.profile.synonyms
                )
                if full is None:
                    partial.append(f"{key}: enrichment unavailable")
                    continue
                groups[key] = full
                fetched += 1
            log.append(
                _log(
                    "enrich",
                    f"round {round_no}: cross-checks fetched for {fetched} of "
                    f"{len(need_enrich)} candidates",
                    compositions=need_enrich,
                    events=len(ctx.events),
                )
            )
        hits: list[tuple[str, LiteratureHit]] = []
        for key in need_classify:
            classified_keys.add(key)
            group = groups.get(key)
            if group is not None and group.literature is not None:
                hits.extend((key, h) for h in group.literature.hits[:cap])
        classified = classifier.classify_hits(
            client=llm, hits=hits, budget=budgets["classify"], cache=cache, model_version=model
        )
        log.extend(classified.entries)
        partial.extend(classified.partial_reasons)
        llm_calls += classified.llm_calls
        cache_hits += classified.cache_hits
        for hit in classified.hits:
            evidence_by_comp.setdefault(hit.composition, []).append(hit)
            all_hits.append(hit)
        scored = score_groups(groups, evidence_by_comp)
    else:
        partial.append(
            f"enrichment stopped after {MAX_ENRICHMENT_ROUNDS} rounds; "
            "top candidates may lack cross-checks"
        )
    # the else clause fires only when the loop ran out of rounds with work left; a round
    # that enriched the last newcomer breaks on the next iteration
    log.append(
        _log(
            "classify",
            f"{len(all_hits)} hits: {llm_calls} classified by the model, {cache_hits} from cache",
        )
    )
    log.extend(scored.decision_log)
    log.append(
        _log(
            "score",
            f"{len([c for c in scored.candidates if c.rank is not None])} ranked, "
            f"{len([c for c in scored.candidates if c.excluded is not None])} excluded",
            actor="scorer",
        )
    )

    # 4. assemble, then rationale and verification
    source_versions = dict(sources.versions)
    if mp_version:
        source_versions["materials_project"] = mp_version
    prompt_hash = prompts.run_prompt_hash(effective) if llm is not None else None
    for c in scored.candidates:
        if c.rank is not None:
            c.rationale_slot = f"candidate:{c.composition}:{rationale.ONE_LINE}"

    def metadata(finished: bool) -> RunMetadata:
        return _run_metadata(
            inputs,
            effective,
            prompt_hash=prompt_hash,
            model=model,
            provider=provider,
            source_versions=source_versions,
            partial_reasons=partial,
            budgets=all_budgets,
            note=scored.note,
            finished=finished,
        )

    bundle = ProvenanceBundle(
        run=metadata(False),
        criteria=ConfirmedCriteria(
            request_text=inputs.request_text,
            parsed_by=outcome.parsed_by,
            confirmed_at=inputs.confirmed_at,
            mode=query.mode,
            candidate_list=list(query.candidate_list),
            effective_settings=query.model_dump(mode="json"),
            clamps=[Clamp(**c.model_dump()) for c in outcome.clamps],
            defaults_applied=list(outcome.defaults_applied),
        ),
        candidates=scored.candidates,
        anchors=scored.anchors,
        evidence=all_hits,
        missing_properties=(
            scored.missing_properties
            if scored.missing_properties is not None
            else missing_markers(inputs.site)
        ),
        decision_log=log,
        availability_events=ctx.events,
    )
    written = rationale.run_rationale(
        client=llm, bundle=bundle, effective=effective, budget=budgets["rationale"]
    )
    log.extend(written.entries)
    if written.partial_reason:
        partial.append(written.partial_reason)
    slots: dict[str, RationaleSlot] = dict(written.slots)
    bundle = bundle.model_copy(update={"rationale": slots})
    bundle, report = verify(bundle)
    log.append(
        _log(
            "verify",
            f"{report.checked_slots} slots and {report.checked_evidence} hits checked; "
            f"{len(report.failures)} failure(s) removed",
            actor="verifier",
            failures=[f.kind for f in report.failures],
        )
    )
    return bundle.model_copy(update={"run": metadata(True), "decision_log": log})
