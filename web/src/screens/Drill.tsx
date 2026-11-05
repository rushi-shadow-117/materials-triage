import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, get, type DrillResponse } from "../api";
import { ScreenHelp } from "../components/Help";

export default function Drill() {
  const { runId = "", composition = "", criterion = "" } = useParams();
  const [d, setD] = useState<DrillResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<DrillResponse>(`/runs/${runId}/drill/${composition}/${criterion}`)
      .then(setD)
      .catch((e) => setError(String(e instanceof ApiError ? e.detail : e)));
  }, [runId, composition, criterion]);

  return (
    <div className="page">
      <p><Link to={`/runs/${runId}`}>← back to the run</Link></p>
      <ScreenHelp screen="drill" />
      {error && (
        <div className="panel bad">
          {error}. This run or value is not available; go back to the run, or open Run history to pick another.
        </div>
      )}
      {d && (
        <>
          <h1>{d.composition} · {d.label} {d.raw}</h1>
          <small className="muted">
            {d.missing_reason ? `missing: ${d.missing_reason}` : `normalized ${d.normalized} × weight ${d.weight} = contribution ${d.contribution}`}
          </small>
          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Where this value came from</h3>
            <dl className="kv">
              <dt>Source</dt><dd>{d.source ?? "none"}</dd>
              <dt>Record id</dt><dd className="mono">{d.record_id ?? "none"}{d.source_url && <> · <a href={d.source_url} target="_blank" rel="noreferrer">open source record</a></>}</dd>
              <dt>Method</dt><dd>{d.method ?? "none"}</dd>
              <dt>{d.fetch_label === "recorded" ? "Recorded" : "Fetched"}</dt><dd className="mono">{d.fetched_at ?? "none"}</dd>
              <dt>Raw response hash</dt><dd className="mono">{d.raw_sha256 ? `sha256:${d.raw_sha256}` : "none"}</dd>
              <dt>Source version</dt><dd className="mono">{d.source_version ?? "not reported"}</dd>
            </dl>
          </div>
          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Same property, other sources</h3>
            {d.other_values.length === 0 ? <p className="muted">No other value of this property in the run.</p> : (
              <table>
                <thead><tr><th>Method</th><th>Form</th><th>Value</th><th>Source · record</th><th>Used</th></tr></thead>
                <tbody>
                  {d.other_values.map((v, i) => (
                    <tr key={i}>
                      <td>{v.method}</td><td>{v.form ?? ""}</td><td className="num">{v.value}</td>
                      <td className="mono">
                        {v.source}{v.record_id ? ` · ${v.record_id}` : ""}
                        {v.url && <> · <a href={v.url} target="_blank" rel="noreferrer">open</a></>}
                      </td>
                      <td>{v.used ? <span className="chip ok">used</span> : "no"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Scoring rule that applies</h3>
            <p>Config entry: <span className="mono">{d.rule_ref ?? "none"}</span></p>
            {d.notes.length > 0 && <ul>{d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
            <p className="muted">Result: normalized {d.normalized} × weight {d.weight} = contribution {d.contribution}. The rule text lives in the config file above; nothing here is written by the model.</p>
          </div>
        </>
      )}
    </div>
  );
}
