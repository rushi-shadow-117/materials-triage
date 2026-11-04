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
import { ScreenHelp, Tip } from "../components/Help";

type Mode = "describe" | "rank";

/** The settings the confirm form edits. Null means "not stated"; the site and profile fill it.
 * Candidate and anchor entries are typed text: the API splits them (config/limits.py) and
 * reports what matched; the browser never parses a formula. */
interface FormSettings {
  mode: "discovery" | "candidate_list";
  candidate_text: string;
  top_n: number | null;
  band_gap_min_ev: number | null;
  band_gap_max_ev: number | null;
  e_above_hull_max_mev: number | null;
  max_elements: number | null;
  extra_anchors_text: string;
  weights: Record<string, number>;
  verbosity: string | null;
  terminology: string | null;
  units: string | null;
  view: string | null;
}

const EMPTY: FormSettings = {
  mode: "discovery",
  candidate_text: "",
  top_n: null,
  band_gap_min_ev: null,
  band_gap_max_ev: null,
  e_above_hull_max_mev: null,
  max_elements: null,
  extra_anchors_text: "",
  weights: {},
  verbosity: null,
  terminology: null,
  units: null,
  view: null,
};

/** Core input limits; the API is the authority (CoreConfig), these only seed the counter
 * until /config/effective answers. */
interface Limits {
  chars: number;
  candidates: number;
}
const DEFAULT_LIMITS: Limits = { chars: 2000, candidates: 50 };

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
  if (s.mode === "candidate_list") out.candidate_text = s.candidate_text;
  if (s.extra_anchors_text.trim()) out.extra_anchors_text = s.extra_anchors_text;
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
  const list = (v: unknown) => (Array.isArray(v) ? (v as string[]).join(", ") : "");
  return {
    mode: settings.mode === "candidate_list" ? "candidate_list" : "discovery",
    candidate_text: list(settings.candidate_list),
    top_n: n(settings.top_n),
    band_gap_min_ev: n(settings.band_gap_min_ev),
    band_gap_max_ev: n(settings.band_gap_max_ev),
    e_above_hull_max_mev: n(settings.e_above_hull_max_mev),
    max_elements: n(settings.max_elements),
    extra_anchors_text: list(settings.extra_anchors),
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
  const [parseSeconds, setParseSeconds] = useState(0);
  const [stoppedAtForm, setStoppedAtForm] = useState<string | null>(null);
  const [form, setForm] = useState<FormSettings | null>(null);
  const [requestedProperties, setRequestedProperties] = useState<string[]>([]);
  const [resolved, setResolved] = useState<ResolveResponse | null>(null);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [bounds, setBounds] = useState<WeightBoundRow[] | null>(null);
  const [limits, setLimits] = useState<Limits>(DEFAULT_LIMITS);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const profileInfo = session.profiles.find((p) => p.id === profile);

  useEffect(() => {
    get<WeightBoundRow[]>(`/weight-bounds?profile=${profile}`)
      .then(setBounds)
      .catch(() => setBounds(null)); // scientists cannot read bounds; sliders then use 0 to 1
    get<{ effective: { core: { max_request_chars: number; max_candidates: number } } }>(`/config/effective?profile=${profile}`)
      .then((r) => setLimits({ chars: r.effective.core.max_request_chars, candidates: r.effective.core.max_candidates }))
      .catch(() => setLimits(DEFAULT_LIMITS));
  }, [profile]);

  // live clamp preview: every edit of the form goes through the same resolve() a run applies
  useEffect(() => {
    if (!form) return;
    const handle = setTimeout(() => {
      post<ResolveResponse>("/criteria/resolve", { profile, settings: compact(form) })
        .then((r) => {
          setResolved(r);
          setResolveError(null);
          setError(null);
        })
        .catch((e) => setResolveError(e instanceof ApiError ? String(e.detail) : String(e)));
    }, 250);
    return () => clearTimeout(handle);
  }, [form, profile]);

  /** What keeps a parsed request from running without the confirm step. Empty means the
   * parse left nothing to confirm: no refusal, nothing missing, no clamp, every named property
   * covered by a criterion. The decision is the server's data; this only reads it. */
  function reasonsToStop(r: ParseResponse): string[] {
    const out: string[] = [];
    if (!r.parse_available) out.push("no model could parse it");
    if (r.refusal) out.push("the request was refused");
    if (r.reason) out.push(r.reason);
    const missing = r.missing_required ?? [];
    const clamps = r.clamps ?? [];
    const uncovered = r.unavailable_properties ?? [];
    const unmatched = r.unresolved_candidates ?? [];
    if (missing.length) out.push(`it does not say: ${missing.join(", ")}`);
    if (clamps.length) out.push(`${clamps.length} value(s) were clamped to site bounds`);
    if (uncovered.length) out.push(`no source covers: ${uncovered.join(", ")}`);
    if (unmatched.length) out.push(`not matched: ${unmatched.join(", ")}`);
    return out;
  }

  async function parse(andRun = false) {
    setParsing(true);
    setParseSeconds(0);
    setError(null);
    setStoppedAtForm(null);
    const timer = setInterval(() => setParseSeconds((n) => n + 1), 1000);
    try {
      const r = await post<ParseResponse>("/parse", { request_text: requestText, profile });
      const parsedForm = fromParsed(r.settings) ?? EMPTY;
      const requested = r.requested_properties ?? [];
      setParsed(r);
      setForm(parsedForm);
      setRequestedProperties(requested);
      if (andRun) {
        const reasons = reasonsToStop(r);
        if (reasons.length === 0) {
          await startRun(parsedForm, requested, "llm");
          return;
        }
        setStoppedAtForm(`Stopped at the form because ${reasons.join("; ")}. Check the settings below and press Confirm and run.`);
      }
    } catch (e) {
      setError(`${String(e instanceof ApiError ? e.detail : e)} You can also fill the criteria form by hand, or use Rank my list.`);
    } finally {
      clearInterval(timer);
      setParsing(false);
    }
  }

  function openRankForm() {
    setParsed(null);
    setResolved(null);
    setForm({ ...EMPTY, mode: "candidate_list", candidate_text: formulas });
  }

  async function run() {
    if (!form) return;
    await startRun(form, requestedProperties, parsed?.parsed_by === "llm" ? "llm" : "form");
  }

  async function startRun(settings: FormSettings, requested: string[], parsedBy: "llm" | "form") {
    setStarting(true);
    setError(null);
    try {
      const matched = (resolved?.settings.candidate_list as string[] | undefined) ?? [];
      const accepted = await post<RunAccepted>("/runs", {
        request_text: mode === "rank" ? `Rank my list: ${matched.join(", ")}` : requestText,
        profile,
        settings: compact(settings),
        requested_properties: requested,
        parsed_by: parsedBy,
      });
      navigate(`/runs/${accepted.run_id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && typeof e.detail === "object" && e.detail && "missing_required" in e.detail) {
        const missing = (e.detail as { missing_required: string[] }).missing_required;
        setError(`Before searching, say what you need: ${missing.join(", ")}. Add a chemistry or a property below, or use Rank my list.`);
      } else {
        setError(`${String(e instanceof ApiError ? e.detail : e)} Nothing was started; fix the form and run again.`);
      }
    } finally {
      setStarting(false);
    }
  }

  const clamps: Clamp[] = resolved?.clamps ?? parsed?.clamps ?? [];
  const overChars = requestText.length > limits.chars;

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
      <ScreenHelp screen="workspace" />

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
              maxLength={limits.chars}
              onChange={(e) => setRequestText(e.target.value)}
            />
            <small className={overChars ? "bad" : "muted"} data-testid="char-count">
              {requestText.length} / {limits.chars} characters
            </small>
            <div className="row">
              {session.me.llm_status === "ok" && (
                <button className="primary" onClick={() => void parse(true)} disabled={parsing || starting || !requestText.trim() || overChars} title="Parse, and run at once when nothing needs confirming; otherwise stop at the form">
                  {parsing ? "Parsing…" : "Parse and run"}
                </button>
              )}
              <button className={session.me.llm_status === "ok" ? "ghost" : "primary"} onClick={() => void parse(false)} disabled={parsing || starting || !requestText.trim() || overChars}>
                {parsing ? "Parsing…" : "Parse, then confirm"}
              </button>
              <button className="ghost" onClick={() => { setParsed(null); setStoppedAtForm(null); setForm(EMPTY); }}>
                Fill the criteria form by hand
              </button>
            </div>
            {parsing && (
              <div className="panel note" role="status" data-testid="parse-progress">
                Reading the request with the model: one call, nothing fetched or scored yet. {parseSeconds}s
              </div>
            )}
            {stoppedAtForm && <div className="panel warn" data-testid="stopped-at-form">{stoppedAtForm}</div>}
            {parsed && !parsed.parse_available && (
              <div className="panel note">{parsed.reason}. The form below is empty; fill it by hand.</div>
            )}
            {parsed?.parse_available && parsed.reason && (
              <div className="panel bad">{parsed.reason}. Reword the request and parse again, or fill the criteria form by hand.</div>
            )}
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
            <p className="muted">
              Formulas or names, separated by commas, semicolons, or new lines; at most {limits.candidates}. Entries that match no formula or
              known name are shown in red and reported as not found; nothing is invented for them.
            </p>
            <textarea aria-label="formulas" placeholder={"HfO2, ZrO2, Al2O3"} value={formulas} onChange={(e) => setFormulas(e.target.value)} />
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
          resolveError={resolveError}
          parsed={parsed}
          limits={limits}
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
  resolveError: string | null;
  parsed: ParseResponse | null;
  limits: Limits;
  requestedProperties: string[];
  setRequestedProperties: (p: string[]) => void;
  onRun: () => void;
  starting: boolean;
}) {
  const { form, setForm, bounds, clamps, resolved, resolveError, parsed, limits } = props;
  const missing = resolved?.missing_required ?? parsed?.missing_required ?? [];
  const unresolved: { text: string; reason: string }[] =
    resolved?.unresolved ??
    (parsed?.unresolved_candidates ?? []).map((text) => ({ text, reason: "not a chemical formula or a known name" }));
  const matched: string[] = (resolved?.settings.candidate_list as string[] | undefined) ?? [];
  const nothingLeft = form.mode === "candidate_list" && unresolved.length > 0 && matched.length === 0;
  const unavailable = parsed?.unavailable_properties ?? [];
  const covered = parsed?.covered_properties ?? [];
  const boundOf = useMemo(() => Object.fromEntries((bounds ?? []).map((b) => [b.criterion, b])), [bounds]);
  const estimate = resolved?.estimated_model_calls ?? null;
  const canRun = !props.starting && missing.length === 0 && !resolveError && (form.mode !== "candidate_list" || matched.length > 0);

  return (
    <div className="panel">
      <h2 style={{ marginTop: 0 }}>Confirm criteria</h2>
      <p className="muted">Nothing has been fetched or scored yet. Edit any value; site bounds apply and every clamp is shown.</p>

      {resolveError && (
        <div className="panel bad" data-testid="resolve-error">
          {resolveError} Run stays off until the form is valid.
        </div>
      )}
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
      {covered.length > 0 && (
        <p className="muted" data-testid="understood-as">
          Understood as: {covered.map((c) => `${c.name} → ${c.criterion.replace(/_/g, " ")}`).join("; ")}.
        </p>
      )}
      {unavailable.length > 0 && (
        <div className="panel warn">
          Not available from configured sources: {unavailable.join(", ")}. These are dropped and listed under "What this screen cannot tell you".
        </div>
      )}
      {unresolved.length > 0 && (
        <div className="panel bad" data-testid="unresolved">
          <p style={{ margin: "0 0 6px" }}>
            {nothingLeft
              ? "None of these matched a formula or a known name; there is nothing to rank yet. Check the spelling or use a formula such as HfO2."
              : "Not matched; the rest are ranked:"}
          </p>
          {unresolved.map((u) => (
            <span key={u.text} className="chip bad" title={u.reason}>
              {u.text} <small>{u.reason}</small>
            </span>
          ))}
        </div>
      )}
      {missing.length > 0 && !nothingLeft && (
        <div className="panel warn">
          {form.mode === "candidate_list" && missing.includes("candidate_list")
            ? "Paste at least one formula or name to rank."
            : `The request does not say what to search for: ${missing.join(", ")}. Add a chemistry or property below, or use Rank my list.`}
        </div>
      )}

      {form.mode === "candidate_list" ? (
        <>
          <label className="field">
            <span>
              Candidates (commas, semicolons, or new lines; at most {limits.candidates})
            </span>
            <textarea
              aria-label="candidates"
              placeholder="HfO2, ZrO2, Al2O3"
              value={form.candidate_text}
              onChange={(e) => setForm({ ...form, candidate_text: e.target.value })}
            />
          </label>
          {matched.length > 0 && (
            <p data-testid="matched" style={{ margin: "0 0 8px" }}>
              <small className="muted">Will be ranked: </small>
              {matched.map((c) => (
                <span key={c} className="chip ok">{c}</span>
              ))}
            </p>
          )}
        </>
      ) : (
        <p className="muted">Discovery: Materials Project is searched with the profile's hard rules; your settings below apply as exclusions in the scorer.</p>
      )}

      <h3>Hard filters</h3>
      <div className="grid2">
        <label className="field">
          <span>Band gap minimum (eV)</span>
          <input type="number" step="0.1" placeholder="profile value" value={form.band_gap_min_ev ?? ""} onChange={(e) => setForm({ ...form, band_gap_min_ev: num(e.target.value) })} />
        </label>
        <label className="field">
          <span>Band gap maximum (eV)</span>
          <input type="number" step="0.1" placeholder="profile value" value={form.band_gap_max_ev ?? ""} onChange={(e) => setForm({ ...form, band_gap_max_ev: num(e.target.value) })} />
        </label>
        <label className="field">
          <span>Energy above hull cutoff (meV/atom) {resolved?.stability_cutoff_mev != null && <em>· effective {resolved.stability_cutoff_mev}</em>}</span>
          <input type="number" step="1" placeholder={resolved?.stability_cutoff_mev != null ? String(resolved.stability_cutoff_mev) : "profile value"} value={form.e_above_hull_max_mev ?? ""} onChange={(e) => setForm({ ...form, e_above_hull_max_mev: num(e.target.value) })} />
        </label>
        <label className="field">
          <span>Max elements</span>
          <input type="number" step="1" min="2" placeholder="profile value" value={form.max_elements ?? ""} onChange={(e) => setForm({ ...form, max_elements: num(e.target.value) })} />
        </label>
        <label className="field">
          <span>Top N</span>
          <input type="number" step="1" min="1" placeholder="10" value={form.top_n ?? ""} onChange={(e) => setForm({ ...form, top_n: num(e.target.value) })} />
        </label>
        <label className="field">
          <span>Compare against (extra anchors, stay ranked)</span>
          <input type="text" placeholder="HfO2, ZrO2" value={form.extra_anchors_text} onChange={(e) => setForm({ ...form, extra_anchors_text: e.target.value })} />
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
              <Tip kind="criterion" id={c}>{c.replace(/_/g, " ")}</Tip> <small className="muted">{b ? `${min} to ${max}` : ""}</small>
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

      {estimate && (
        <p className="muted" data-testid="estimate">
          {estimate.total > 0
            ? `This run may make up to ${estimate.total} model calls (hard cap ${estimate.cap}): ${estimate.basis}.`
            : estimate.basis}
        </p>
      )}

      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" onClick={props.onRun} disabled={!canRun}>
          {props.starting ? "Starting…" : "Confirm and run"}
        </button>
        {resolved && <small className="muted">config sha {resolved.config_sha.slice(0, 12)}</small>}
      </div>
    </div>
  );
}
