import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, type RunSummary } from "../api";

export default function History() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  useEffect(() => {
    get<RunSummary[]>("/runs").then(setRuns).catch(() => setRuns([]));
  }, []);
  return (
    <div className="page">
      <h1>Run history</h1>
      <div className="panel">
        {!runs ? (
          <p className="muted">Loading…</p>
        ) : runs.length === 0 ? (
          <p className="muted">No runs yet.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Started</th><th>Request</th><th>Profile</th><th>Status</th><th>Ranked</th><th>Excluded</th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td className="mono">{r.started_at?.replace("T", " ").slice(0, 19)}</td>
                  <td><Link to={`/runs/${r.run_id}`}>{r.request_text || r.run_id.slice(0, 8)}</Link></td>
                  <td>{r.profile}</td>
                  <td>{r.status}{r.partial ? " (partial)" : ""}</td>
                  <td className="num">{r.ranked ?? ""}</td>
                  <td className="num">{r.excluded ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="muted">Compare two runs from the command line: <code>materials-triage diff RUN_A RUN_B</code>.</p>
    </div>
  );
}
