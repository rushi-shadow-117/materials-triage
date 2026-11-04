import { useEffect, useState } from "react";
import { ApiError, get, post, postYaml, type HazardRow, type HealthResponse, type LayerRow, type ProfileValidation, type WeightBoundRow } from "../api";
import type { Session } from "../App";

type Tab = "effective" | "hazard" | "bounds" | "profiles" | "health";

export default function Console({ session }: { session: Session }) {
  const isAdmin = session.me.role === "admin";
  const [tab, setTab] = useState<Tab>("effective");
  const [profile, setProfile] = useState(session.profiles[0]?.id ?? "oxide_dielectric_thin_film");
  return (
    <div className="page">
      <h1>Console</h1>
      <p className="muted">
        Where the rules behind every score live. Configuration is read-only here and shows which layer set each value.
        {isAdmin ? " Admins may request a source refresh; FDEs and admins may upload scoring profiles." : " As a field engineer you may upload scoring profiles; hazard policy, bounds and refresh are the site admin's."}
      </p>
      <div className="tabs">
        {(["effective", "hazard", "bounds", "profiles", "health"] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {{ effective: "Effective configuration", hazard: "Hazard policy", bounds: "Weight bounds", profiles: "Profiles (YAML)", health: "Source health" }[t]}
          </button>
        ))}
      </div>
      {(tab === "effective" || tab === "bounds") && (
        <label className="field" style={{ maxWidth: 360 }}>
          <span>For profile</span>
          <select value={profile} onChange={(e) => setProfile(e.target.value)}>
            {session.profiles.map((p) => <option key={p.id} value={p.id}>{p.name} v{p.version}</option>)}
          </select>
        </label>
      )}
      {tab === "effective" && <Layers profile={profile} />}
      {tab === "hazard" && <Hazard />}
      {tab === "bounds" && <Bounds profile={profile} />}
      {tab === "profiles" && <Profiles />}
      {tab === "health" && <Health isAdmin={isAdmin} />}
    </div>
  );
}

function useLoad<T>(path: string): [T | null, string | null] {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setData(null);
    get<T>(path).then(setData).catch((e) => setError(String(e instanceof ApiError ? e.detail : e)));
  }, [path]);
  return [data, error];
}

function Layers({ profile }: { profile: string }) {
  const [rows, error] = useLoad<LayerRow[]>(`/config/layers?profile=${profile}`);
  return (
    <div className="panel">
      <p className="muted">Read only. Layers apply in order core, site, profile, query; site bounds clamp everything after them. The "set by" column names the layer whose value survived.</p>
      {error && <div className="panel bad">{error}</div>}
      {rows && (
        <table>
          <thead><tr><th>Key</th><th>Effective</th><th>Core</th><th>Site</th><th>Profile</th><th>Query</th><th>Set by</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td className="mono">{r.key}</td><td><strong>{r.effective ?? "—"}</strong></td>
                <td className={r.set_by === "core" ? "chip" : undefined}>{r.core ?? "—"}</td>
                <td>{r.site ?? "—"}</td><td>{r.profile ?? "—"}</td><td>{r.query ?? "—"}</td><td>{r.set_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Hazard() {
  const [rows, error] = useLoad<HazardRow[]>("/hazard-policy");
  return (
    <div className="panel">
      {error && <div className="panel bad">{error}</div>}
      {rows && (
        <table>
          <thead><tr><th>Element or compound</th><th>Tier</th><th>Reason</th><th>Source citation (config entry)</th></tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i}><td>{r.subject}</td><td>{r.tier}</td><td>{r.reason ?? ""}</td><td className="mono">{r.source_ref}</td></tr>)}</tbody>
        </table>
      )}
      <p className="muted">Compounds with no PubChem record resolve to "unknown" and score neutral, never allow. Scientists cannot change this policy; it is edited in config/hazard_policy.yaml with a cited source per entry.</p>
    </div>
  );
}

function Bounds({ profile }: { profile: string }) {
  const [rows, error] = useLoad<WeightBoundRow[]>(`/weight-bounds?profile=${profile}`);
  return (
    <div className="panel">
      {error && <div className="panel bad">{error}</div>}
      {rows && (
        <table>
          <thead><tr><th>Criterion</th><th>Min</th><th>Max</th><th>Profile default</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.criterion}><td>{r.criterion}</td><td className="num">{r.min}</td><td className="num">{r.max}</td><td className="num">{r.profile_default}</td></tr>)}</tbody>
        </table>
      )}
      <p className="muted">Scientists move weights only inside these bounds. Profiles that exceed them fail validation.</p>
    </div>
  );
}

function Profiles() {
  const [yaml, setYaml] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [result, setResult] = useState<ProfileValidation | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function validate() {
    setError(null); setSaved(null);
    try { setResult(await postYaml<ProfileValidation>("/admin/profiles/validate", yaml)); }
    catch (e) { setError(String(e instanceof ApiError ? e.detail : e)); }
  }
  async function save() {
    setError(null);
    try {
      const r = await postYaml<{ file: string; id: string }>("/admin/profiles", yaml);
      setSaved(`Saved as ${r.file}. It appears in the profile list as ${r.id}.`);
    } catch (e) { setError(String(e instanceof ApiError ? e.detail : e)); }
  }
  const errors = result?.issues.filter((i) => i.level === "error") ?? [];
  const warnings = result?.issues.filter((i) => i.level === "warning") ?? [];
  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>Upload scoring profile</h3>
      <p className="muted">Validated with the scorer's own loader before anything is saved. A saved profile is a new file; existing files are never overwritten.</p>
      <input type="file" accept=".yaml,.yml" onChange={async (e) => { const f = e.target.files?.[0]; if (f) { setFileName(f.name); setYaml(await f.text()); setResult(null); } }} />
      {fileName && <small className="muted"> {fileName}</small>}
      <textarea aria-label="profile yaml" style={{ minHeight: 220, fontFamily: "ui-monospace, monospace" }} value={yaml} onChange={(e) => { setYaml(e.target.value); setResult(null); }} />
      <div className="row">
        <button className="primary" onClick={validate} disabled={!yaml.trim()}>Validate</button>
        <button className="ghost" onClick={save} disabled={!result?.ok}>{result?.ok ? `Save as ${result.profile} v${result.version}` : `Fix ${errors.length || ""} error${errors.length === 1 ? "" : "s"} to save`}</button>
      </div>
      {error && <div className="panel bad">{error}</div>}
      {saved && <div className="panel note">{saved}</div>}
      {result && (
        <>
          <p>{errors.length} error{errors.length === 1 ? "" : "s"}, {warnings.length} warning{warnings.length === 1 ? "" : "s"}.</p>
          {result.issues.map((i, k) => <div key={k} className={`issue ${i.level}`}><span className="mono">{i.path}</span> · {i.message}</div>)}
          {result.clamp_preview.length > 0 && (
            <>
              <h3>Clamp preview (a default query under this profile)</h3>
              <table><thead><tr><th>Setting</th><th>Requested</th><th>Effective</th><th>Bound</th></tr></thead>
                <tbody>{result.clamp_preview.map((c) => <tr key={c.setting}><td className="mono">{c.setting}</td><td>{String(c.requested)}</td><td>{String(c.applied)}</td><td className="mono">{c.bound}</td></tr>)}</tbody></table>
            </>
          )}
        </>
      )}
    </div>
  );
}

function Health({ isAdmin }: { isAdmin: boolean }) {
  const [health, error] = useLoad<HealthResponse>("/health");
  const [source, setSource] = useState("materials_project");
  const [note, setNote] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function refresh() {
    setErr(null);
    try {
      const r = await post<{ applies_to: string }>("/admin/refresh", { source, note });
      setDone(`Refresh of ${source} accepted; it applies to ${r.applies_to}. Recorded in the audit log.`);
      setNote("");
    } catch (e) { setErr(String(e instanceof ApiError ? e.detail : e)); }
  }
  return (
    <div className="panel">
      {error && <div className="panel bad">{error}</div>}
      {health && (
        <>
          <p className="muted">Fetch source {health.fetch_source} ({health.fetch_mode}); model {health.llm_model ?? "none"} via {health.llm_provider}; classify {health.classify_mode}; auth {health.auth_mode}.</p>
          <table>
            <thead><tr><th>Source</th><th>Status</th><th>Via</th><th>Last fetch</th><th>Records</th><th>Allowed host</th></tr></thead>
            <tbody>{health.sources.map((s) => <tr key={s.source}><td>{s.source}</td><td>{s.status}</td><td>{s.fetch_source}</td><td className="mono">{s.last_fetch ?? "—"}</td><td className="num">{s.records ?? "—"}</td><td className="mono">{s.allowed_host ?? "—"}</td></tr>)}</tbody>
          </table>
        </>
      )}
      {isAdmin && (
        <div className="panel note" style={{ marginTop: 12 }}>
          <h3 style={{ marginTop: 0 }}>Refresh source cache</h3>
          <p className="muted">Admin only. Recorded in the audit log. Runs started after the refresh use new data; earlier runs keep their snapshot and hashes and remain reproducible.</p>
          <div className="row">
            <select value={source} onChange={(e) => setSource(e.target.value)} style={{ maxWidth: 240 }}>
              <option value="materials_project">materials_project</option><option value="openalex">openalex</option><option value="pubchem">pubchem</option>
            </select>
            <input type="text" placeholder="Audit note (required)" value={note} onChange={(e) => setNote(e.target.value)} style={{ maxWidth: 420 }} />
            <button className="primary" disabled={!note.trim()} onClick={refresh}>Refresh now</button>
          </div>
          {done && <p>{done}</p>}
          {err && <div className="panel bad">{err}</div>}
        </div>
      )}
    </div>
  );
}
