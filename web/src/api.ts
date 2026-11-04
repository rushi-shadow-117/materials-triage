// One small fetch wrapper. The API lives at the same origin (served by `materials-triage
// serve`) or behind the Vite dev proxy at /api. The bearer token is the only place a role can
// come from; the UI never sends a role.
import type { components } from "./api/types";

export type Schemas = components["schemas"];
export type ProfileSummary = Schemas["ProfileSummary"];
export type RunSummary = Schemas["RunSummary"];
export type RunAccepted = Schemas["RunAccepted"];
export type ParseResponse = Schemas["ParseResponse"];
export type ResolveResponse = Schemas["ResolveResponse"];
// Progress events travel over SSE, so they are not in the OpenAPI schema; this mirrors
// api/schemas.py ProgressEvent.
export interface ProgressEvent {
  at: string;
  step: string;
  summary: string;
  actor: string;
  by: "code" | "llm";
}
export type LayerRow = Schemas["LayerRow"];
export type HazardRow = Schemas["HazardRow"];
export type WeightBoundRow = Schemas["WeightBoundRow"];
export type ProfileValidation = Schemas["ProfileValidation"];
export type HealthResponse = Schemas["HealthResponse"];
export type DrillResponse = Schemas["DrillResponse"];
export type RelaxChoice = Schemas["RelaxChoice"];
export type Me = Schemas["Me"];
export type Clamp = ResolveResponse["clamps"][number];

const BASE = "/api"; // the API lives only under /api, in dev and in the built app
const TOKEN_KEY = "materials-triage.token";

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the token lives for this page only */
  }
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

function headers(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra ?? {}) };
  const token = getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* no JSON body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export async function get<T>(path: string): Promise<T> {
  return parse<T>(await fetch(`${BASE}${path}`, { headers: headers() }));
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  return parse<T>(
    await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: headers({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    }),
  );
}

export async function postYaml<T>(path: string, yaml: string): Promise<T> {
  return parse<T>(
    await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: headers({ "Content-Type": "application/yaml" }),
      body: yaml,
    }),
  );
}

export async function getText(path: string): Promise<string> {
  const res = await fetch(`${BASE}${path}`, { headers: headers() });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.text();
}

export function exportUrl(runId: string, format: "json" | "csv" | "md", view: string): string {
  return `${BASE}/runs/${runId}/export?format=${format}&view=${view}`;
}

/** Subscribe to a run's progress. EventSource cannot send headers, so the stream is read with
 * fetch and parsed by hand; `onDone` fires once with the final status. */
export async function streamEvents(
  runId: string,
  onEvent: (e: ProgressEvent) => void,
  onDone: (e: ProgressEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/runs/${runId}/events`, { headers: headers(), signal });
  if (!res.ok || !res.body) throw new ApiError(res.status, res.statusText);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      if (!data.length) continue;
      const payload = JSON.parse(data.join("\n")) as ProgressEvent;
      if (event === "done") onDone(payload);
      else if (event === "step") onEvent(payload);
    }
  }
}
