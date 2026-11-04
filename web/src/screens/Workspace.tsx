import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  post,
  type Clamp,
  type ParseResponse,
  type ResolveResponse,
  type RunAccepted,
  type WeightBoundRow,
} from "../api";
import { get } from "../api";
import type { Session } from "../App";

type Mode = "describe" | "rank";

/** The settings the confirm form edits. Null means "not stated"; the site and profile fill it. */
interface FormSettings {
  mode: "discovery" | "candidate_list";
  candidate_list: string[];
  top_n: number | null;
  band_gap_min_ev: number | null;
  band_gap_max_ev: number | null;
  e_above_hull_max_mev: number | null;
  max_elements: number | null;
  extra_anchors: string[];
  weights: Record<string, number>;
  verbosity: string | null;
  terminology: string | null;
  units: string | null;
  view: string | null;
}

const EMPTY: FormSettings = {
  mode: "discovery",
  candidate_list: [],
  top_n: null,
  band_gap_min_ev: null,
  band_gap_max_ev: null,
  e_above_hull_max_mev: null,
  max_elements: null,
  extra_anchors: [],
  weights: {},
  verbosity: null,
  terminology: null,
  units: null,
  view: null,
};

const CRITERIA = [
  "stability",
  "band_gap",
  "hazard",
  "simplicity",
  "evidence",
  "dielectric_constant",
  "deposition_method",
  "cost",
];

function compact(s: FormSettings): Record<string, unknown> {
  const out: Record<string, unknown> = { mode: s.mode };
  if (s.candidate_list.length) out.candidate_list = s.candidate_list;
  if (s.extra_anchors.length) out.extra_anchors = s.extra_anchors;
  for (const k of ["top_n", "band_gap_min_ev", "band_gap_max_ev", "e_above_hull_max_mev", "max_elements", "verbosity", "terminology", "units", "view"] as const) {
    if (s[k] !== null && s[k] !== undefined && s[k] !== ("" as unknown)) out[k] = s[k];
  }
  if (Object.keys(s.weights).length) out.weights = s.weights;
  return out;
}

function fromParsed(settings: Record<string, unknown> | null | undefined): FormSettings {
  if (!settings) return EMPTY;
  const n = (v: unknown) => (typeof v === "number" ? v : null);
  const str = (v: unknown) => (typeof v === "string" ? v : null);
  return {
    mode: settings.mode === "candidate_list" ? "candidate_list" : "discovery",
    candidate_list: Array.isArray(settings.candidate_list) ? (settings.candidate_list as string[]) : [],
    top_n: n(settings.top_n),
    band_gap_min_ev: n(settings.band_gap_min_ev),
    band_gap_max_ev: n(settings.band_gap_max_ev),
    e_above_hull_max_mev: n(settings.e_above_hull_max_mev),
    max_elements: n(settings.max_elements),
    extra_anchors: Array.isArray(settings.extra_anchors) ? (settings.extra_anchors as string[]) : [],
    weights: (settings.weights as Record<string, number>) ?? {},
    verbosity: str(settings.verbosity),
    terminology: str(settings.terminology),
    units: str(settings.units),
    view: str(settings.view),
  };
}

export default function Workspace({ session }: { session: Session }) {
  const navigate = useNavigate();
  const [profile, setProfile] = useState(session.profiles[0]?.id ?? "oxide_dielectric_thin_film");
  const [mode, setMode] = useState<Mode>("describe");
  const [requestText, setRequestText] = useState("");
  const [formulas, setFormulas] = useState("");
  const [parsed, setParsed] = useState<ParseResponse | null>(null);
  const [parsing, setParsing] = useState(false);
  const [form, setForm] = useState<FormSettings | null>(null);
  const [requestedProperties, setRequestedProperties] = useState<string[]>([]);
  const [resolved, setResolved] = useState<ResolveResponse | null>(null);
  const [bounds, setBounds] = useState<WeightBoundRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const profileInfo = session.profiles.find((p) => p.id === profile);

  useEffect(() => {
    get<WeightBoundRow[]>(`/weight-bounds?profile=${profile}`)
      .then(setBounds)
      .catch(() => setBounds(null)); // scientists cannot read bounds; sliders then use 0 to 1
  }, [profile]);

  // live clamp preview: every edit of the form goes through the same resolve() a run applies
  useEffect(() => {
    if (!form) return;
    const handle = setTimeout(() => {
      post<ResolveResponse>("/criteria/resolve", { profile, settings: compact(form) })
        .then((r) => {
          setResolved(r);
          setError(null);
        })
        .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
    }, 250);
    return () => clearTimeout(handle);
  }, [form, profile]);

  async function parse() {
    setParsing(true);
    setError(null);
    try {
      const r = await post<ParseResponse>("/parse", { request_text: requestText, profile });
      setParsed(r);
      setForm(fromParsed(r.settings) ?? EMPTY);
      setRequestedProperties([]);
    } catch (e) {
      setError(String(e instanceof ApiError ? e.detail : e));
    } finally {
      setParsing(false);
    }
  }

  function openRankForm() {
    const list = formulas
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    setParsed(null);
    setForm({ ...EMPTY, mode: "candidate_list", candidate_list: list });
  }

  async function run() {
    if (!form) return;
    setStarting(true);
    setError(null);
    try {
      const accepted = await post<RunAccepted>("/runs", {
        request_text: mode === "rank" ? `Rank my list: ${form.candidate_list.join(", ")}` : requestText,
        profile,
        settings: compact(form),
        requested_properties: requestedProperties,
        parsed_by: parsed?.parsed_by === "llm" ? "llm" : "form",
      });
      navigate(`/runs/${accepted.run_id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && typeof e.detail === "object" && e.detail && "missing_required" in e.detail) {
        const missing = (e.detail as { missing_required: string[] }).missing_required;
        setError(`Before searching, say what you need: ${missing.join(", ")}. Add a chemistry or a property below, or use Rank my list.`);
      } else {
        setError(String(e instanceof ApiError ? e.detail : e));
      }
    } finally {
      setStarting(false);
    }
  }

  const clamps: Clamp[] = resolved?.clamps ?? parsed?.clamps ?? [];

  return (
    <div className="page">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>Workspace</h1>
        <label className="field" style={{ margin: 0, minWidth: 320 }}>
          <span>Profile</span>
          <select value={profile} onChange={(e) => { setProfile(e.target.value); setForm(null); setParsed(null); }}>
            {session.profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} v{p.version}
              </option>
            ))}
          </select>
        </label>
      </div>
      {profileInfo?.description && <p className="muted">{profileInfo.description}</p>}

      <div className="panel">
        <div className="tabs">
          <button className={mode === "describe" ? "active" : ""} onClick={() => setMode("describe")}>Describe a request</button>
          <button className={mode === "rank" ? "active" : ""} onClick={() => setMode("rank")}>Rank my list</button>
        </div>
        {mode === "describe" ? (
          <>
            <p className="muted">
              The model only parses this text into criteria you confirm below. Every score is computed in code from public database records.
            </p>
            <textarea
              aria-label="request"
              placeholder="Find promising oxide dielectric candidates for thin-film experiments. Prefer stable materials, wide band gaps, non-toxic elements, simple compositions, and public evidence."
              value={requestText}
              onChange={(e) => setRequestText(e.target.value)}
            />
            <div className="row">
              <button className="primary" onClick={parse} disabled={parsing || !requestText.trim()}>
                {parsing ? "Parsing…" : "Parse request"}
              </button>
              <button className="ghost" onClick={() => { setParsed(null); setForm(EMPTY); }}>
                Fill the criteria form by hand
              </button>
            </div>
            {parsed && !parsed.parse_available && (
              <div className="panel note">{parsed.reason}. The form below is empty; fill it by hand.</div>
            )}
            {parsed?.parse_available && parsed.reason && <div className="panel bad">{parsed.reason}</div>}
            {parsed?.refusal && (
              <div className="panel bad">
                <strong>Request refused.</strong> {parsed.refusal}
                <p className="muted">Nothing was fetched or scored. Remove that part of the request, or use Rank my list.</p>
              </div>
            )}
            {parsed?.parse_available && !parsed.refusal && (
              <p className="muted">Parsed by {parsed.parsed_by} ({parsed.model ?? "model"}). Nothing has been fetched or scored yet.</p>
            )}
          </>
        ) : (
          <>
            <p className="muted">Formulas, one per line or comma separated. Names that are not formulas are reported as not found; nothing is invented for them.</p>
            <textarea aria-label="formulas" placeholder={"HfO2\nZrO2\nAl2O3"} value={formulas} onChange={(e) => setFormulas(e.target.value)} />
            <button className="primary" onClick={openRankForm} disabled={!formulas.trim()}>
              Review criteria
            </button>
          </>
        )}
      </div>

      {form && !parsed?.refusal && (
        <ConfirmForm
          form={form}
          setForm={setForm}
          bounds={bounds}
          clamps={clamps}
          resolved={resolved}
          parsed={parsed}
          requestedProperties={requestedProperties}
          setRequestedProperties={setRequestedProperties}
          onRun={run}
          starting={starting}
        />
      )}
      {error && <div className="panel bad">{error}</div>}
    </div>
  );
}

function num(v: string): number | null {
  return v.trim() === "" ? null : Number(v);
}

function ConfirmForm(props: {
  form: FormSettings;
  setForm: (f: FormSettings) => void;
  bounds: WeightBoundRow[] | null;
  clamps: Clamp[];
  resolved: ResolveResponse | null;
  parsed: ParseResponse | null;
  requestedProperties: string[];
  setRequestedProperties: (p: string[]) => void;
  onRun: () => void;
  starting: boolean;
}) {
  const { form, setForm, bounds, clamps, resolved, parsed } = props;
  const missing = resolved?.missing_required ?? parsed?.missing_required ?? [];
  const unresolved = resolved?.unresolved_candidates ?? parsed?.unresolved_candidates ?? [];
  const unavailable = parsed?.unavailable_properties ?? [];
  const boundOf = useMemo(() => Object.fromEntries((bounds ?? []).map((b) => [b.criterion, b])), [bounds]);

  return (
    <div className="panel">
      <h2 style={{ marginTop: 0 }}>Confirm criteria</h2>
      <p className="muted">Nothing has been fetched or scored yet. Edit any value; site bounds apply and every clamp is shown.</p>

      {clamps.length > 0 && (
        <div className="panel warn">
          {clamps.length} value{clamps.length > 1 ? "s" : ""} clamped.
          <ul style={{ margin: "4px 0 0" }}>
            {clamps.map((c) => (
              <li key={c.setting}>
                {c.setting}: you asked for {String(c.requested)}; site bound is {c.bound}. Using {String(c.applied)}.
              </li>
            ))}
          </ul>
        </div>
      )}
      {unavailable.length > 0 && (
        <div className="panel warn">
          Not available from configured sources: {unavailable.join(", ")}. These are dropped and listed under "What this screen cannot tell you".
        </div>
      )}
      {unresolved.length > 0 && (
        <div className="panel warn">Not chemical formulas: {unresolved.join(", ")}. They are reported as not found; the rest are ranked.</div>
      )}
      {missing.length > 0 && (
        <div className="panel warn">The request does not say what to search for: {missing.join(", ")}. Add a chemistry or property below, or use Rank my list.</div>
      )}

      {form.mode === "candidate_list" ? (
        <label className="field">
          <span>Candidates (reduced formulas)</span>
          <input
            type="text"
            value={form.candidate_list.join(", ")}
            onChange={(e) => setForm({ ...form, candidate_list: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
          />
        </label>
      ) : (
        <p className="muted">Discovery: Materials Project is searched with the profile's hard rules; your settings below apply as exclusions in the scorer.</p>
      )}

      <h3>Hard filters</h3>
      <div className="grid2">
        <label className="field">
          <span>Band gap minimum (eV)</span>
          <input type="number" step="0.1" value={form.band_gap_min_ev ?? ""} onChange={(e) => setForm({ ...form, band_gap_min_ev: num(e.target.value) })} />
        </label>
        <label className="field">
          <span>Band gap maximum (eV)</span>
          <input type="number" step="0.1" value={form.band_gap_max_ev ?? ""} onChange={(e) => setForm({ ...form, band_gap_max_ev: num(e.target.value) })} />
        </label>
        <label className="field">
          <span>Energy above hull cutoff (meV/atom) {resolved?.stability_cutoff_mev != null && <em>· effective {resolved.stability_cutoff_mev}</em>}</span>
          <input type="number" step="1" value={form.e_above_hull_max_mev ?? ""} onChange={(e) => setForm({ ...form, e_above_hull_max_mev: num(e.target.value) })} />
        </label>
        <label className="field">
          <span>Max elements</span>
          <input type="number" step="1" min="2" value={form.max_elements ?? ""} onChange={(e) => setForm({ ...form, max_elements: num(e.target.value) })} />
        </label>
        <label className="field">
          <span>Top N</span>
          <input type="number" step="1" min="1" value={form.top_n ?? ""} onChange={(e) => setForm({ ...form, top_n: num(e.target.value) })} />
        </label>
        <label className="field">
          <span>Compare against (extra anchors, stay ranked)</span>
          <input type="text" placeholder="HfO2" value={form.extra_anchors.join(", ")} onChange={(e) => setForm({ ...form, extra_anchors: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
        </label>
      </div>
      <p className="muted">
        Anion policy and hazard policy are set by the profile and the site admin and are not editable here. Hazard: exclude radioactive elements and IARC Group 1 elements, flag the admin's flag list; "non-toxic" maps to this policy.
      </p>

      <h3>Weights</h3>
      <p className="muted">Within site bounds. A weight left blank uses the profile value.</p>
      {CRITERIA.map((c) => {
        const b = boundOf[c];
        const min = b?.min ?? 0;
        const max = b?.max ?? 1;
        const value = form.weights[c] ?? b?.profile_default ?? (resolved?.effective_weights[c] ?? 0);
        return (
          <div className="slider" key={c}>
            <span>
              {c.replace(/_/g, " ")} <small className="muted">{b ? `${min} to ${max}` : ""}</small>
            </span>
            <input
              type="range"
              min={min}
              max={max}
              step={0.05}
              value={value}
              aria-label={`weight ${c}`}
              onChange={(e) => setForm({ ...form, weights: { ...form.weights, [c]: Number(e.target.value) } })}
            />
            <span className="mono">{Number(value).toFixed(2)}</span>
          </div>
        );
      })}

      <h3>Output</h3>
      <div className="grid2">
        <label className="field"><span>Verbosity</span>
          <select value={form.verbosity ?? ""} onChange={(e) => setForm({ ...form, verbosity: e.target.value || null })}>
            <option value="">site default</option><option value="concise">concise</option><option value="standard">standard</option><option value="detailed">detailed</option>
          </select></label>
        <label className="field"><span>Terminology</span>
          <select value={form.terminology ?? ""} onChange={(e) => setForm({ ...form, terminology: e.target.value || null })}>
            <option value="">site default</option><option value="technical">technical</option><option value="general">general (glossary applied)</option>
          </select></label>
        <label className="field"><span>Units</span>
          <select value={form.units ?? ""} onChange={(e) => setForm({ ...form, units: e.target.value || null })}>
            <option value="">eV</option><option value="eV">eV</option><option value="meV">meV</option>
          </select></label>
      </div>

      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={props.onRun} disabled={props.starting || missing.length > 0}>
          {props.starting ? "Starting…" : "Confirm and run"}
        </button>
        {resolved && <small className="muted">config sha {resolved.config_sha.slice(0, 12)}</small>}
      </div>
    </div>
  );
}
