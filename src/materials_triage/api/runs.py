"""Runs started from the API: the same pipeline pieces the CLI uses, run on a small thread
pool, with every decision-log entry streamed to subscribers as it happens.

A run's events are buffered so a subscriber that connects late sees them all. Cancel is
cooperative: the flag is checked between pipeline steps (inside the event callback), the run
raises RunCancelledError, and no bundle is saved.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from materials_triage.adapters.base import Call, RawResponse, Source
from materials_triage.adapters.runner import Runner
from materials_triage.adapters.transport import HttpxTransport
from materials_triage.agent import pipeline
from materials_triage.agent.parse import ParseOutcome
from materials_triage.cli import wiring
from materials_triage.cli.runs import RunStore
from materials_triage.provenance.store import Store, make_engine
from materials_triage.records.bundle import DecisionLogEntry, FetchMode, ProvenanceBundle
from materials_triage.settings import Settings

from .schemas import ProgressEvent, RunStatus

LLM_ACTORS = {"agent", "llm", "model"}


@dataclass
class RunState:
    run_id: UUID
    profile: str
    request_text: str
    status: RunStatus = "queued"
    events: list[ProgressEvent] = field(default_factory=list)
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    changed: threading.Condition = field(default_factory=threading.Condition)

    def push(self, event: ProgressEvent) -> None:
        with self.changed:
            self.events.append(event)
            self.changed.notify_all()

    def finish(self, status: RunStatus, error: str | None = None) -> None:
        with self.changed:
            self.status = status
            self.error = error
            self.finished_at = datetime.now(UTC)
            self.done.set()
            self.changed.notify_all()


def _by(entry: DecisionLogEntry) -> str:
    return "llm" if entry.actor in LLM_ACTORS else "code"


class RunManager:
    def __init__(
        self,
        settings: Settings,
        store: RunStore,
        sources: pipeline.Sources,
        *,
        workers: int = 2,
    ) -> None:
        self.settings = settings
        self.store = store
        self.sources = sources
        self.states: dict[str, RunState] = {}
        self.pending_refresh: set[str] = set()  # sources the next store-backed run refetches
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="run")
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ starting

    def start(
        self,
        outcome: ParseOutcome,
        layers: wiring.Layers,
        *,
        request_text: str,
        profile_id: str,
        extra_log: list[DecisionLogEntry] | None = None,
    ) -> RunState:
        state = RunState(run_id=uuid4(), profile=profile_id, request_text=request_text)
        with self._lock:
            self.states[str(state.run_id)] = state
        self._pool.submit(self._execute, state, outcome, layers, extra_log or [])
        return state

    def _fetch(self, run_id: UUID) -> tuple[pipeline.Fetch, FetchMode, str, set[str]]:
        source, line = wiring.resolve_fetch_source(self.settings, "auto")
        refresh = set(self.pending_refresh) if source == "store" else set()
        if source == "cassettes" or not refresh or self.settings.fetch_mode == "replay":
            fetch, mode = wiring.make_fetch(self.settings, source, run_id=run_id)
            return fetch, mode, line, set()
        # A refresh was requested: calls to those sources go through a refresh-mode runner,
        # everything else through the normal one. Both write to the same store.
        store = Store(make_engine(self.settings.database_url))
        transport = HttpxTransport(self.settings, sleep=time.sleep)
        store_mode = self.settings.fetch_mode or "live"
        normal = Runner(store, transport, mode=store_mode, run_id=run_id)
        refreshing = Runner(store, transport, mode="refresh", run_id=run_id)
        wanted = {Source(s) for s in refresh}

        def routed(call: Call) -> RawResponse | None:
            runner = refreshing if call.source in wanted else normal
            fetched = runner.try_fetch(call)
            return None if fetched is None else fetched.raw

        self.pending_refresh.clear()
        return routed, FetchMode(store_mode), line, refresh

    def _execute(
        self,
        state: RunState,
        outcome: ParseOutcome,
        layers: wiring.Layers,
        extra_log: list[DecisionLogEntry],
    ) -> None:
        state.status = "running"

        def on_event(entry: DecisionLogEntry) -> None:
            state.push(
                ProgressEvent(
                    at=entry.at.isoformat(),
                    step=entry.step,
                    summary=entry.summary,
                    actor=entry.actor,
                    by=_by(entry),  # type: ignore[arg-type]
                )
            )
            if state.cancel.is_set():
                raise pipeline.RunCancelledError("cancelled by the researcher")

        try:
            fetch, mode, fetch_line, refreshed = self._fetch(state.run_id)
            notes = [
                DecisionLogEntry(
                    at=datetime.now(UTC), actor="api", step="fetch_source", summary=fetch_line
                ),
                *extra_log,
            ]
            if refreshed:
                notes.append(
                    DecisionLogEntry(
                        at=datetime.now(UTC),
                        actor="api",
                        step="refresh",
                        summary=f"admin refresh applied to {sorted(refreshed)} for this run",
                    )
                )
            for n in notes:
                on_event(n)
            inputs = pipeline.RunInputs(
                request_text=state.request_text,
                parse=outcome,
                core=layers.core,
                site=layers.site,
                profile=layers.profile,
                hazard_policy=layers.hazard_policy,
                confirmed_at=datetime.now(UTC),
                fetch_mode=mode,
                run_id=state.run_id,
                classify_mode=self.settings.classify_mode,
            )
            llm = wiring.make_llm(self.settings, no_llm=self.settings.llm_provider == "none")
            bundle = pipeline.run(
                inputs,
                fetch=fetch,
                sources=self.sources,
                scorer=wiring.make_scorer(),
                llm=llm,
                cache=wiring.make_cache(self.settings),
                on_event=on_event,
            )
            bundle = bundle.model_copy(update={"decision_log": [*notes, *bundle.decision_log]})
            self.store.save(bundle)
            state.finish("refused" if bundle.criteria.mode == "refused" else "completed")
        except pipeline.RunCancelledError:
            state.finish("cancelled")
        except Exception as e:  # noqa: BLE001 - the run fails visibly; nothing is invented
            state.finish("failed", f"{type(e).__name__}: {e}")

    # ------------------------------------------------------------------ reading

    def get(self, run_id: str) -> RunState | None:
        return self.states.get(run_id)

    def cancel(self, run_id: str) -> bool:
        state = self.states.get(run_id)
        if state is None or state.done.is_set():
            return False
        state.cancel.set()
        return True

    def stream(self, run_id: str, *, poll_s: float = 0.25) -> Iterator[dict[str, Any]]:
        """Every event so far, then new ones as they arrive, then one `done` event."""
        state = self.states[run_id]
        sent = 0
        while True:
            with state.changed:
                while sent >= len(state.events) and not state.done.is_set():
                    state.changed.wait(timeout=poll_s)
                batch = state.events[sent:]
                sent = len(state.events)
                finished = state.done.is_set()
            for e in batch:
                yield {"event": "step", "data": e.model_dump_json()}
            if finished and sent >= len(state.events):
                yield {
                    "event": "done",
                    "data": ProgressEvent(
                        at=(state.finished_at or datetime.now(UTC)).isoformat(),
                        step="done",
                        summary=state.status if state.error is None else state.error,
                        actor="api",
                        by="code",
                    ).model_dump_json(),
                }
                return

    def load_bundle(self, run_id: str) -> ProvenanceBundle:
        return self.store.load(run_id)
