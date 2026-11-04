import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, exportUrl, get, post, streamEvents, type ProgressEvent, type RunAccepted, type RunSummary } from "../api";
import type { Session } from "../App";
import type { RowView, RunViewJson } from "../view";

export default function RunPage({ session }: { session: Session }) {
  const { runId = "" } = useParams();
  const [status, setStatus] = useState<RunSummary | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [view, setView] = useState<"pi_summary" | "audit">("pi_summary");
  const [data, setData] = useState<RunViewJson | null>(null);
  const [error, setError] = useState<string | null>(null);
  const started = useRef<number>(Date.now());
  const [elapsed, setElapsed] = useState(0);

  // status, then the event stream while the run is live
  useEffect(() => {
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setInterval> | null = null;
    (async () => {
      try {
        const s = await get<RunSummary>(`/runs/${runId}/status`);
        setStatus(s);
        if (s.started_at) started.current = new Date(s.started_at).getTime();
        if (s.status === "queued" || s.status === "running") {
          timer = setInterval(() => setElapsed(Math.round((Date.now() - started.current) / 1000)), 500);
          await streamEvents(
            runId,
            (e) => setEvents((prev) => [...prev, e]),
            async () => {
              setStatus(await get<RunSummary>(`/runs/${runId}/status`));
            },
            ctrl.signal,
          );
        }
      } catch (e) {
        if (!(e instanceof DOMException)) setError(String(e instanceof ApiError ? e.detail : e));
      } finally {
        if (timer) clearInterval(timer);
      }
    })();
    return () => {
      ctrl.abort();
      if (timer) clearInterval(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (!status || (status.status !== "completed" && status.status !== "refused")) return;
    get<RunViewJson>(`/runs/${runId}/view?view=${view}`)
      .then(setData)
      .catch((e) => setError(String(e instanceof ApiError ? e.detail : e)));
  }, [runId, view, status]);

  const live = status?.status === "queued" || status?.status === "running";

  return (
    <div className="page">
      {status && (
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <h1>{status.request_text || "Run"}</h1>
            <small className="muted">
              Run {runId.slice(0, 8)} · profile {status.profile} · {status.status}
              {status.partial ? " · partial" : ""}
            </small>
          </div>
          {live && (
            <button className="ghost" onClick={() => post(`/runs/${runId}/cancel`, {}).catch(() => undefined)}>
              Cancel run
            </button>
          )}
        </div>
      )}
      {error && <div className="panel bad">{error}</div>}

      {(live || (events.length > 0 && !data)) && (
        <div className="panel">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>{live ? "Running" : "Finished"}</strong>
            <span className="mono">{String(Math.floor(elapsed / 60)).padStart(2, "0")}:{String(elapsed % 60).padStart(2, "0")} elapsed</span>
          </div>
          <ul className="steps">
            {events.map((e, i) => (
              <li key={i}>
                <span className={`chip ${e.by}`}>{e.by === "llm" ? "LLM" : "code"}</span>
                <span>
                  <strong>{e.step}</strong> · {e.summary}
                </span>
                <span className="time">{e.at.slice(11, 19)}</span>
              </li>
            ))}
          </ul>
          <p className="muted">Results appear when verification finishes. If a source fails, the run continues and results are marked partial.</p>
        </div>
      )}

      {status?.status === "failed" && <div className="panel bad">Run failed: {status.error}</div>}
      {status?.status === "cancelled" && <div className="panel warn">Run cancelled. Nothing was saved.</div>}

      {data && data.view !== view && <p className="muted">Loading the {view === "audit" ? "audit" : "PI"} view…</p>}
      {data && data.view === view && <Results data={data} view={view} setView={setView} runId={runId} session={session} />}
    </div>
  );
}

function Results({ data, view, setView, runId }: { data: RunViewJson; view: "pi_summary" | "audit"; setView: (v: "pi_summary" | "audit") => void; runId: string; session: Session }) {
  const navigate = useNavigate();
  const [relaxing, setRelaxing] = useState(false);
  const ranked = data.rows.length;
  const r = data.run;
  const terminologyGeneral = data.criteria.effective_settings["terminology"] === "general";

  async function relax(choiceId: string) {
    setRelaxing(true);
    try {
      const accepted = await post<RunAccepted>(`/runs/${runId}/relax`, { choice_id: choiceId });
      navigate(`/runs/${accepted.run_id}`);
    } finally {
      setRelaxing(false);
    }
  }

  if (data.refusal) {
    return (
      <div className="panel bad">
        <strong>Request refused.</strong> {data.refusal}
        <p className="muted">Nothing was fetched or scored. Only configured public sources are used.</p>
        <Link to="/">Edit request</Link>
      </div>
    );
  }

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <small className="muted">
          {ranked} ranked · {data.excluded.length + data.hidden_excluded} excluded · completed {r.finished_at?.slice(11, 19) ?? "-"} ·{" "}
          {r.fetch_mode} data · verifier {data.verifier ? (data.verifier.passed ? "passed" : `${data.verifier.failures.length} removed`) : "not run (no model text)"}
        </small>
        <div className="row">
          <div className="tabs" style={{ margin: 0, border: "none" }}>
            <button className={view === "pi_summary" ? "active" : ""} onClick={() => setView("pi_summary")}>PI summary</button>
            <button className={view === "audit" ? "active" : ""} onClick={() => setView("audit")}>Audit view</button>
          </div>
          <span className="muted">Export</span>
          <a href={exportUrl(runId, "md", view)} target="_blank" rel="noreferrer">Markdown</a>
          <a href={exportUrl(runId, "csv", view)} target="_blank" rel="noreferrer">CSV</a>
          <a href={exportUrl(runId, "json", view)} target="_blank" rel="noreferrer">JSON</a>
        </div>
      </div>

      {r.partial && (
        <div className="panel warn">
          <strong>Partial results.</strong> {data.partial_reasons.join("; ")}
        </div>
      )}
      {data.unresolved_candidates.length > 0 && (
        <div className="panel warn">Not found in any source: {data.unresolved_candidates.join(", ")}. These names are not chemical formulas; nothing is shown for them.</div>
      )}
      {data.unavailable_properties.length > 0 && (
        <div className="panel warn">Not available from configured sources: {data.unavailable_properties.join(", ")}. Not scored; no value is shown.</div>
      )}
      {data.overview && <p>{data.overview}</p>}

      {data.relaxations && data.relaxations.length > 0 && (
        <div className="panel note">
          <strong>Too few results.</strong> Only {ranked} candidate{ranked === 1 ? "" : "s"} passed your filters. Each option below was counted by re-scoring the fetched set; nothing is applied until you choose.
          <ul>
            {data.relaxations.map((c) => (
              <li key={c.choice_id} className="row">
                <span>{c.text} ({c.admits.join(", ")})</span>
                <button className="ghost" disabled={relaxing} onClick={() => relax(c.choice_id)}>Apply as a new run</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Rank</th><th>Material</th><th>Score</th><th>Why</th><th>Key caveat</th><th>Evidence</th><th>k</th><th>Missing</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => <Row key={row.composition} row={row} runId={runId} audit={view === "audit"} />)}
            {data.anchors.map((row) => <Row key={`anchor-${row.composition}`} row={row} runId={runId} audit={view === "audit"} />)}
          </tbody>
        </table>
        {data.ties_note && <p className="muted" data-testid="ties-note">{data.ties_note}</p>}
        {data.hidden_ranked > 0 && <p className="muted">{data.hidden_ranked} more ranked rows beyond top N; export the CSV or JSON for all of them.</p>}
        <p className="muted">
          Scores are computed in code (weighted mean of normalized criteria). Rationale and caveats are checked against the score table before display. A missing value is shown as missing and never scored as zero.
        </p>
      </div>

      {view === "audit" && data.rows.concat(data.anchors).map((row) => <AuditRow key={`audit-${row.composition}`} row={row} runId={runId} />)}

      <h2>Excluded ({data.excluded.length + data.hidden_excluded}) · removed before ranking by rule</h2>
      <div className="panel">
        {data.excluded.length === 0 ? <p className="muted">None.</p> : (
          <table>
            <thead><tr><th>Material</th><th>Rule</th><th>Detail</th><th>Rule source</th></tr></thead>
            <tbody>
              {data.excluded.map((row) => (
                <tr key={row.composition}>
                  <td>{view === "audit" ? <Link to={`/runs/${runId}/rows/${row.composition}/stability`}>{row.composition}</Link> : row.composition}</td>
                  <td className="mono">{row.exclusion}</td>
                  <td>{row.exclusion_detail}</td>
                  <td className="mono">{row.exclusion_ref}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted">Excluded materials are never ranked. Hazard rules are set by the site admin; scientists cannot override them.</p>
      </div>

      {Object.keys(data.caveat_texts).length > 0 && (
        <>
          <h2>Caveats</h2>
          <div className="panel">
            <dl className="kv">
              {Object.entries(data.caveat_texts).map(([id, c]) => (
                <div key={id} style={{ display: "contents" }}>
                  <dt className="mono">{id}</dt>
                  <dd>{c.text} <small className="muted">({c.source})</small></dd>
                </div>
              ))}
            </dl>
          </div>
        </>
      )}

      <h2>What this screen cannot tell you</h2>
      <div className="panel">
        <p className="muted">Not in configured public sources. Measure or consult the literature before committing deposition time.</p>
        <ul>
          {data.missing_properties.map((m) => <li key={m}>{m}</li>)}
          {data.unavailable_properties.map((m) => <li key={`u-${m}`}>{m} (requested; no configured source)</li>)}
        </ul>
      </div>

      <h2>Settings applied</h2>
      <div className="panel">
        <dl className="kv">
          <dt>Defaults</dt><dd>{data.defaults_applied.join("; ") || "none"}</dd>
          <dt>Clamps</dt><dd>{data.clamps.join("; ") || "none"}</dd>
          {data.hull_cutoff && (<><dt>Energy above hull cutoff</dt><dd>{data.hull_cutoff}</dd></>)}
          <dt>Terminology</dt><dd>{terminologyGeneral ? "general (glossary applied in Markdown)" : "technical"}</dd>
          {view === "audit" && (<>
            <dt>Config sha</dt><dd className="mono">{r.config_sha}</dd>
            <dt>Profile</dt><dd>{r.profile_name} v{r.profile_version}; hazard policy v{r.policy_version}</dd>
            <dt>Prompt hash</dt><dd className="mono">{r.prompt_hash ?? "none (no LLM)"}</dd>
            <dt>Model</dt><dd>{r.model_version ?? "none"} {r.provider ? `(${r.provider})` : ""}</dd>
            <dt>Source versions</dt><dd className="mono">{Object.entries(r.source_versions).map(([k, v]) => `${k}=${v}`).join(", ") || "none"}</dd>
            <dt>Budgets</dt><dd>{data.budgets.join("; ") || "none recorded"}</dd>
          </>)}
        </dl>
      </div>

      {view === "audit" && (
        <>
          <h2>Verification</h2>
          <div className="panel">
            {data.verifier ? (
              <>
                <p>{data.verifier.checked_slots} rationale slots and {data.verifier.checked_evidence} evidence quotes checked; {data.verifier.failures.length} failed and were withheld, never silently fixed.</p>
                {data.verifier.failures.length > 0 && (
                  <table><thead><tr><th>Kind</th><th>Where</th><th>Fragment</th><th>Action</th></tr></thead>
                    <tbody>{data.verifier.failures.map((f, i) => <tr key={i}><td className="mono">{f.kind}</td><td className="mono">{f.location}</td><td>{f.fragment}</td><td>{f.action}</td></tr>)}</tbody></table>
                )}
              </>
            ) : <p className="muted">No model text in this run, so nothing to verify.</p>}
          </div>
          <h2>Decision log</h2>
          <div className="panel">
            <ul className="steps">
              {data.decision_log.map((d, i) => (
                <li key={i}><span className="chip">{d.actor}</span><span><strong>{d.step}</strong> · {d.summary}</span><span className="time">{d.at.slice(11, 19)}</span></li>
              ))}
            </ul>
          </div>
          <details><summary>Markdown source of this view</summary><pre className="md">{data.markdown}</pre></details>
        </>
      )}
    </>
  );
}

function Row({ row, runId, audit }: { row: RowView; runId: string; audit: boolean }) {
  const cell = (criterion: string, text: string) =>
    audit ? <Link to={`/runs/${runId}/rows/${row.composition}/${criterion}`}>{text}</Link> : <>{text}</>;
  return (
    <tr className={row.is_anchor ? "anchor" : undefined} data-composition={row.composition}>
      <td className="num">{row.is_anchor ? "Ref" : row.rank}</td>
      <td>
        <strong>{row.composition}</strong>
        {row.is_anchor && <div><small className="muted">{row.rank}. Shown for calibration; not a candidate.</small></div>}
        {row.flags.length > 0 && <div>{row.flags.map((f) => <span key={f} className={`chip ${f.includes("hazard") || f.includes("conflict") ? "warn" : ""}`} style={{ marginRight: 4 }}>{f.replace(/_/g, " ")}</span>)}</div>}
      </td>
      <td className="num">{cell("band_gap", row.total)}</td>
      <td>{row.rationale || <span className="muted">no rationale (no model)</span>}</td>
      <td>{row.key_caveat}</td>
      <td>{cell("evidence", row.evidence_tier)}</td>
      <td className="num">{cell("dielectric_constant", row.k)}</td>
      <td>{row.missing.length ? row.missing.join(", ") : "none"}</td>
    </tr>
  );
}

function AuditRow({ row, runId }: { row: RowView; runId: string }) {
  return (
    <details className="panel">
      <summary>
        {row.is_anchor ? "Reference" : `#${row.rank}`} {row.composition} · score {row.total}
        {row.sensitivity ? ` · ${row.sensitivity}` : ""}
      </summary>
      <h3>Score breakdown</h3>
      <table>
        <thead><tr><th>Criterion</th><th>Raw</th><th>Source</th><th>Normalized</th><th>Weight</th><th>Contribution</th><th>Record</th></tr></thead>
        <tbody>
          {(row.criteria ?? []).map((c) => (
            <tr key={c.criterion}>
              <td><Link to={`/runs/${runId}/rows/${row.composition}/${c.criterion}`}>{c.label}</Link></td>
              <td className="num">{c.missing ? <span className="muted">missing ({c.missing_reason})</span> : c.raw}</td>
              <td>{c.source}</td>
              <td className="num">{c.normalized}</td>
              <td className="num">{c.weight}</td>
              <td className="num">{c.contribution}</td>
              <td className="mono">{c.provenance ? `${c.provenance.source} ${c.provenance.record_id}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">Total (computed in code) {row.total}. Band gap source: {row.band_gap_source ?? "none"}. Structural dimensionality: {row.dimensionality}.</p>
      {row.polymorphs && (
        <>
          <h3>Polymorphs ({row.polymorphs.total}: {row.polymorphs.observed} observed, {row.polymorphs.theoretical} theoretical)</h3>
          <table>
            <thead><tr><th>MP id</th><th>Space group</th><th>Energy above hull</th><th>Observed</th><th>Excluded</th></tr></thead>
            <tbody>
              {row.polymorphs.top_by_hull.map((p) => (
                <tr key={p.mp_id}><td className="mono">{p.mp_id}</td><td>{p.spacegroup}</td><td className="num">{p.hull}</td><td>{p.observed}</td><td className="mono">{p.excluded_rule ?? ""}</td></tr>
              ))}
            </tbody>
          </table>
          {row.polymorphs.ground_state_is_theoretical && <p className="chip warn">ground state is theoretical</p>}
        </>
      )}
      {row.evidence && row.evidence.length > 0 && (
        <>
          <h3>Evidence ({row.evidence_tier}) · {row.literature}</h3>
          <ul>
            {row.evidence.map((e) => (
              <li key={e.openalex_id}>
                <span className={`chip ${e.verified ? "ok" : "warn"}`}>{e.verified ? "verified" : "not verified"}</span> {e.label}
                {e.deposition_method ? ` · ${e.deposition_method}` : ""} · <a href={e.url ?? undefined} target="_blank" rel="noreferrer">{e.openalex_id}</a>
                {e.quote && <blockquote style={{ margin: "4px 0 0 12px" }}>"{e.quote}"</blockquote>}
                {e.note && <small className="muted"> {e.note}</small>}
              </li>
            ))}
          </ul>
        </>
      )}
      {row.ghs && <p><strong>Hazard:</strong> {row.ghs}{row.echa_attribution ? " · Source: European Chemicals Agency, https://echa.europa.eu/" : ""}</p>}
      {row.caveats.length > 0 && (
        <ul>{row.caveats.map((c, i) => <li key={i}><span className="mono">{c.id}</span>: {c.text} <small className="muted">({c.source})</small></li>)}</ul>
      )}
    </details>
  );
}
