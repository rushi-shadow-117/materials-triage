// The run view the API serves at /runs/{id}/view: the render package's view model as JSON.
// Every value is already a formatted string; the browser never formats a number.

export interface ProvenanceView {
  source: string;
  record_id: string;
  method: string | null;
  fetched_at: string;
  source_version: string | null;
  url: string | null;
  license: string | null;
}

export interface CriterionView {
  criterion: string;
  label: string;
  raw: string;
  source: string;
  normalized: string;
  weight: string;
  contribution: string;
  missing: boolean;
  missing_reason: string | null;
  provenance: ProvenanceView | null;
  notes: string[];
}

export interface PolymorphRowView {
  mp_id: string;
  spacegroup: string;
  hull: string;
  observed: string;
  excluded_rule: string | null;
  hull_provenance: ProvenanceView | null;
}

export interface PolymorphView {
  total: string;
  observed: string;
  theoretical: string;
  unknown: string;
  ground_state: PolymorphRowView | null;
  ground_state_is_theoretical: boolean | null;
  lowest_observed: PolymorphRowView | null;
  scored_is_ground_state: boolean;
  hull_status_conflict: boolean;
  top_by_hull: PolymorphRowView[];
}

export interface EvidenceView {
  openalex_id: string;
  label: string;
  deposition_method: string | null;
  quote: string | null;
  verified: boolean;
  note: string | null;
  title: string | null;
  year: string | null;
  url: string | null;
}

export interface CaveatText {
  id: string;
  subject: string | null;
  text: string;
  source: string;
  entered: boolean;
}

export interface ValueView {
  label: string;
  text: string;
  provenance: ProvenanceView | null;
}

export interface RowView {
  composition: string;
  is_anchor: boolean;
  rank: string;
  tied?: boolean;
  total: string;
  rationale: string;
  rationale_verified: boolean | null;
  key_caveat: string;
  caveats: CaveatText[];
  flags: string[];
  evidence_tier: string;
  k: string;
  missing: string[];
  exclusion: string | null;
  exclusion_detail: string | null;
  exclusion_ref: string | null;
  echa_attribution: boolean;
  gaps: string;
  band_gap_source: string | null;
  // audit view only
  removed_fragments?: string[];
  criteria?: CriterionView[];
  polymorphs?: PolymorphView;
  ghs?: string;
  gap_values?: ValueView[];
  reference_values?: ValueView[];
  literature?: string;
  evidence?: EvidenceView[];
  sensitivity?: string | null;
  dimensionality?: string;
}

export interface RunMeta {
  run_id: string;
  started_at: string;
  finished_at: string | null;
  profile_name: string;
  profile_version: string;
  policy_version: string;
  config_sha: string;
  prompt_hash: string | null;
  model_version: string | null;
  provider: string | null;
  fetch_mode: string;
  partial: boolean;
  partial_reasons: string[];
  source_versions: Record<string, string>;
  budgets_used: Record<string, number>;
  budgets_limit: Record<string, number>;
  note: string | null;
}

export interface Criteria {
  request_text: string;
  parsed_by: string;
  confirmed_at: string | null;
  mode: string;
  candidate_list: string[];
  effective_settings: Record<string, unknown>;
  clamps: { setting: string; requested: unknown; applied: unknown; bound: string }[];
  defaults_applied: string[];
  unresolved_candidates: string[];
  unavailable_properties: string[];
  stability_cutoff_mev: number | null;
}

export interface VerifierFailure {
  kind: string;
  location: string;
  fragment: string;
  action: string;
}

export interface Verifier {
  checked_slots: number;
  checked_evidence: number;
  failures: VerifierFailure[];
  passed: boolean;
}

export interface DecisionLogEntry {
  at: string;
  actor: string;
  step: string;
  summary: string;
  detail: Record<string, unknown>;
}

export interface RelaxChoiceView {
  choice_id: string;
  setting: string;
  current: number | null;
  proposed: number;
  adds: number;
  admits: string[];
  text: string;
}

export interface RunViewJson {
  view: "pi_summary" | "audit";
  rows: RowView[];
  excluded: RowView[];
  anchors: RowView[];
  refusal: string | null;
  overview: string | null;
  missing_properties: string[];
  partial_reasons: string[];
  clamps: string[];
  defaults_applied: string[];
  budgets: string[];
  caveat_texts: Record<string, CaveatText>;
  hidden_ranked: number;
  hidden_excluded: number;
  hull_cutoff: string | null;
  unresolved_candidates: string[];
  unavailable_properties: string[];
  ties_note: string | null;
  profile_caveats: CaveatText[];
  run: RunMeta;
  criteria: Criteria;
  verifier: Verifier | null;
  markdown: string;
  decision_log: DecisionLogEntry[];
  relaxations?: RelaxChoiceView[];
}
