import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { ApiError, get, getToken, setDevRole, setToken, type Me, type ProfileSummary } from "./api";
import Workspace from "./screens/Workspace";
import RunPage from "./screens/RunPage";
import Drill from "./screens/Drill";
import Console from "./screens/Console";
import History from "./screens/History";
import { OIDC_ENABLED, finishSignIn, signIn, signOut } from "./oidc";

export interface Session {
  me: Me;
  profiles: ProfileSummary[];
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const navigate = useNavigate();

  async function load() {
    setError(null);
    try {
      const me = await get<Me>("/me");
      const profiles = await get<ProfileSummary[]>("/profiles");
      setSession({ me, profiles });
    } catch (e) {
      setSession(null);
      setError(e instanceof ApiError && e.status === 401 ? "sign in" : String(e));
    }
  }

  useEffect(() => {
    if (OIDC_ENABLED && window.location.pathname === "/callback") {
      finishSignIn()
        .then(() => {
          navigate("/", { replace: true });
          void load();
        })
        .catch((e) => setError(String(e)));
      return;
    }
    void load();
  }, []);

  if (!session) {
    return (
      <div className="page">
        <h1>Materials Triage</h1>
        {error === "sign in" && OIDC_ENABLED ? (
          <div className="panel">
            <p>Sign in with your site account. Your role comes from the identity provider.</p>
            <button className="primary" onClick={() => void signIn()}>
              Sign in
            </button>
          </div>
        ) : error === "sign in" ? (
          <div className="panel">
            <p>This site needs a bearer token. Paste the token you were given.</p>
            <form
              className="row"
              onSubmit={(e) => {
                e.preventDefault();
                setToken(tokenInput.trim() || null);
                void load();
              }}
            >
              <input
                type="text"
                aria-label="bearer token"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                style={{ maxWidth: 360 }}
              />
              <button className="primary" type="submit">
                Sign in
              </button>
            </form>
          </div>
        ) : error ? (
          <div className="panel bad">API not reachable: {error}</div>
        ) : (
          <p className="muted">Loading…</p>
        )}
      </div>
    );
  }

  const { me } = session;
  const console_ok = me.role === "fde" || me.role === "admin";
  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand">
          Materials Triage
        </NavLink>
        <nav>
          <NavLink to="/">Workspace</NavLink>
          <NavLink to="/runs">Run history</NavLink>
          {console_ok && <NavLink to="/console">Console</NavLink>}
        </nav>
        <span className="chip" title={`auth mode ${me.auth_mode}`}>
          Role: {me.role}
        </span>
        {me.role_switch && (
          <label className="field" style={{ margin: 0 }} title="Development only (AUTH_MODE=none). In static and OIDC modes the role comes from the token.">
            <select
              aria-label="dev role"
              value={me.role}
              onChange={(e) => {
                setDevRole(e.target.value);
                void load();
              }}
            >
              <option value="scientist">try as scientist</option>
              <option value="fde">try as fde</option>
              <option value="admin">try as admin</option>
            </select>
          </label>
        )}
        <small className="muted">{me.subject}</small>
        {getToken() && (
          <button
            className="ghost"
            onClick={() => {
              if (OIDC_ENABLED) {
                void signOut();
                return;
              }
              setToken(null);
              setSession(null);
              setError("sign in");
              navigate("/");
            }}
          >
            Sign out
          </button>
        )}
      </header>
      {me.llm_status !== "ok" && (
        <div className="banner" role="status" data-llm-status={me.llm_status}>
          {me.llm_note}
        </div>
      )}
      <Routes>
        <Route path="/" element={<Workspace session={session} />} />
        <Route path="/runs" element={<History />} />
        <Route path="/runs/:runId" element={<RunPage session={session} />} />
        <Route path="/runs/:runId/rows/:composition/:criterion" element={<Drill />} />
        <Route
          path="/console/*"
          element={console_ok ? <Console session={session} /> : <Forbidden role={me.role} />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

function Forbidden({ role }: { role: string }) {
  return (
    <div className="page">
      <div className="panel bad">
        The console is for site admins and field engineers. Your role is {role}. Settings cannot
        be changed from the workspace or the chat.
      </div>
    </div>
  );
}
