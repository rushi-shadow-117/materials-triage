// Every plain-language help text in the app, in one file for owner review (Track H item 2).
// Each entry says where its wording comes from; none states chemistry on its own authority.
// tests/test_help_text.py checks that every criterion, flag, caveat, exclusion rule, evidence
// tier, and screen the code can show has an entry here, and that each is marked for review.

export interface HelpEntry {
  text: string;
  source: string;
  review: "owner";
}

export const SCREEN_HELP: Record<string, HelpEntry> = {
  workspace: {
    text: "Describe what you want, or paste a list of formulas. The model only turns a description into the criteria form; you confirm or edit the form before anything is fetched, and every score is computed in code from public records. Rank my list needs no model. The form shows every clamp the site applies and, before you run, how many model calls the run may make.",
    source: "docs/SCIENTIST_GUIDE.md, Two ways in and Confirming criteria",
    review: "owner",
  },
  results: {
    text: "One row per ranked candidate: rank, score, a one-line rationale, the key caveat, the evidence tier, the dielectric constant where a source has it, and what is missing. The reference row shows where the incumbent would place and never takes a slot. Read the panel above the table first: it lists what no configured source can tell you. The audit view expands every number to its source record; the chart plots band gap against dielectric constant for every scored candidate that has both.",
    source: "docs/SCIENTIST_GUIDE.md, Reading the result",
    review: "owner",
  },
  drill: {
    text: "Where one value came from: the record id, method, fetch time, raw response hash, the other values of the same property the run holds and which one was used, and the config entry with the rule that chose. Nothing on this page is written by the model.",
    source: "docs/SCIENTIST_GUIDE.md, Drill-down",
    review: "owner",
  },
  console: {
    text: "The rules behind every score, read-only: each configured value with the layer that set it, the hazard policy with its cited sources, the weight bounds, the sources' health, and (for field engineers and admins) scoring profile upload. Profiles are saved as new versions; nothing here is edited in place, and no role can change a role.",
    source: "docs/ADMIN_GUIDE.md, The console; docs/PERMISSIONS.md",
    review: "owner",
  },
  history: {
    text: "Every run this server has saved, newest first. A run keeps its data snapshot and hashes, so an old result stays reproducible; compare two runs from the command line with materials-triage diff.",
    source: "docs/ARCHITECTURE.md, Determinism and replay",
    review: "owner",
  },
  help: {
    text: "The scientist guide and the admin guide, served from the docs folder of this installation so they match the running version.",
    source: "docs/SCIENTIST_GUIDE.md; docs/ADMIN_GUIDE.md",
    review: "owner",
  },
};

export const CRITERION_HELP: Record<string, HelpEntry> = {
  stability: {
    text: "Energy above the convex hull from Materials Project, in meV per atom; 0 means on the hull. Scored on a linear ramp from 1 at 0 to 0 at the profile's cutoff; above the cutoff the candidate is excluded.",
    source: "config/scoring_profiles/*.yaml, criteria.stability.shape",
    review: "owner",
  },
  band_gap: {
    text: "The band gap that scores, in the profile's source order: experimental where a compendium has it, then TBmBJ from JARVIS, then PBE from Materials Project. Every source is shown side by side, and a disagreement above the configured tolerance is flagged.",
    source: "docs/SCIENTIST_GUIDE.md, Some things to know: Band gaps",
    review: "owner",
  },
  hazard: {
    text: "The site's hazard policy, by element first and then by the compound's PubChem GHS record: exclude, flag, or allow, each entry citing a public source. A compound with no record is unknown and scores neutral, never allow.",
    source: "config/hazard_policy.yaml; Console, Hazard policy tab",
    review: "owner",
  },
  simplicity: {
    text: "The number of elements and the anion policy (strict oxide, strict nitride, or any). Fewer elements score higher, a ternary may carry a penalty, and a composition over the maximum is excluded.",
    source: "docs/CONFIGURING.md, criteria.simplicity",
    review: "owner",
  },
  evidence: {
    text: "The best verified evidence label among the composition's paper abstracts, as an ordinal tier. Without a usable label the criterion is missing and carries no weight.",
    source: "config/scoring_profiles/*.yaml, criteria.evidence.shape",
    review: "owner",
  },
  dielectric_constant: {
    text: "The computed static dielectric constant from Materials Project (DFPT) against the profile's target band. Missing where no source has it, and never scored as zero.",
    source: "config/scoring_profiles/*.yaml, criteria.dielectric_constant.shape",
    review: "owner",
  },
  deposition_method: {
    text: "1 when any evidence hit names a deposition method in the site's list, 0 when hits name methods and none match, missing otherwise. Weight 0 unless the profile enters it.",
    source: "config/scoring_profiles/*.yaml, criteria.deposition_method.shape",
    review: "owner",
  },
  cost: {
    text: "No public cost or abundance source is wired, so this criterion is always missing. A documented extension.",
    source: "config/scoring_profiles/*.yaml, criteria.cost.note",
    review: "owner",
  },
};

export const FLAG_HELP: Record<string, HelpEntry> = {
  hull_status_conflict: {
    text: "The hull energies the run holds for this composition disagree about whether the scored structure is stable.",
    source: "records/bundle.py, Flag",
    review: "owner",
  },
  near_cutoff: {
    text: "The scored energy above hull sits inside the profile's near-cutoff band just below the stability cutoff.",
    source: "config/scoring_profiles/*.yaml, criteria.stability.near_cutoff_band_mev_per_atom",
    review: "owner",
  },
  ground_state_is_theoretical: {
    text: "The structure that was scored has not been reported as made; it exists only as a computed entry.",
    source: "docs/SCIENTIST_GUIDE.md, Some things to know: Polymorphs",
    review: "owner",
  },
  polymorph_requested: {
    text: "You named a Materials Project id, so that polymorph was scored instead of the ground state.",
    source: "records/bundle.py, Flag",
    review: "owner",
  },
  band_gap_conflict: {
    text: "Two band gap sources differ by more than the profile's tolerance. Both are shown; the profile's fallback source scores.",
    source: "docs/SCIENTIST_GUIDE.md, Some things to know: Band gaps",
    review: "owner",
  },
  band_gap_single_source: {
    text: "Only one band gap source is available for this composition, so nothing could be cross-checked.",
    source: "records/bundle.py, Flag",
    review: "owner",
  },
  band_gap_sources_uncompared: {
    text: "More than one band gap source exists but the profile sets no tolerance, so they were not compared.",
    source: "records/bundle.py, Flag",
    review: "owner",
  },
  pbe_only_below_window: {
    text: "Only a computed PBE gap is available and it sits between the discovery floor and the profile's minimum; the candidate is kept and scored, with the PBE caveat.",
    source: "docs/DECISIONS.md, PBE-only gaps",
    review: "owner",
  },
  hazard_flag: {
    text: "An element or a GHS code on the site's flag list. The candidate stays ranked and carries the policy's caveat.",
    source: "config/hazard_policy.yaml, tiers.flag",
    review: "owner",
  },
  hazard_unknown: {
    text: "No hazard record was found for this compound. It scores neutral and is never treated as safe.",
    source: "Console, Hazard policy tab note",
    review: "owner",
  },
  process_hazard: {
    text: "GHS particulate codes or a per-material policy entry mark a handling hazard. The candidate stays, with the policy's caveat.",
    source: "config/hazard_policy.yaml, tiers.process_hazard.description",
    review: "owner",
  },
  anion_undetermined: {
    text: "No oxidation-state guess settled which element is the anion; shown as a flag under the any policy.",
    source: "records/bundle.py, Flag",
    review: "owner",
  },
  evidence_unclassified: {
    text: "The abstracts were not classified (no model, no cached label, or the budget was reached), so the evidence criterion is missing for this row.",
    source: "docs/SCIENTIST_GUIDE.md, Some things to know: Evidence tiers",
    review: "owner",
  },
  enrichment_missing: {
    text: "Only summary-level data was fetched for this row; the cross-checks (polymorphs, other gap sources, literature, hazard record) were not run.",
    source: "records/bundle.py, Flag",
    review: "owner",
  },
};

export const CAVEAT_HELP: Record<string, HelpEntry> = {
  band_offsets_not_checked: {
    text: "Band offsets to your substrate are in no configured source. Applies to every row.",
    source: "docs/SCIENTIST_GUIDE.md, What this screen cannot tell you",
    review: "owner",
  },
  stability_cutoff_hull_mismatch: {
    text: "The stability cutoff was calibrated on one hull and the scored value comes from another (Materials Project's mixed GGA, GGA+U, r2SCAN hull).",
    source: "config/scoring_profiles/*.yaml, criteria.stability",
    review: "owner",
  },
  stability_cutoff_oxide_calibrated: {
    text: "The stability cutoff was calibrated on oxides; under a non-oxide anion policy it is applied as it stands.",
    source: "config/scoring_profiles/*.yaml, criteria.stability.anion_calibration_note",
    review: "owner",
  },
  experimental_gap_composition_level: {
    text: "The experimental band gap is reported for the composition, not for a specific polymorph.",
    source: "docs/DECISIONS.md, The composition-level gap note is profile-wide",
    review: "owner",
  },
  experimental_gap_unreferenced: {
    text: "An experimental gap value whose source table gives no reference for it.",
    source: "records/bundle.py, CaveatId",
    review: "owner",
  },
  reference_value_pending: {
    text: "A configured reference value whose citation is still pending verification; it is shown and not used.",
    source: "config/reference_values.yaml, status: pending",
    review: "owner",
  },
  attribution_echa: {
    text: "The GHS data shown derives from the European Chemicals Agency and is shown with that attribution.",
    source: "config/site_profile.default.yaml, attribution.echa",
    review: "owner",
  },
};

export const EXCLUSION_HELP: Record<string, HelpEntry> = {
  "stability.cutoff": { text: "Energy above hull is over the profile's cutoff.", source: "config/scoring_profiles/*.yaml, criteria.stability", review: "owner" },
  "band_gap.hard_min": { text: "The scored band gap is below the hard minimum.", source: "config/scoring_profiles/*.yaml, criteria.band_gap", review: "owner" },
  "band_gap.hard_max": { text: "The scored band gap is above the hard maximum.", source: "config/scoring_profiles/*.yaml, criteria.band_gap", review: "owner" },
  "hazard.radioactive_exclude": { text: "Contains a radioactive element; excluded by default and admin-locked.", source: "config/hazard_policy.yaml", review: "owner" },
  "hazard.exclude": { text: "Contains an element in the policy's exclude tier.", source: "config/hazard_policy.yaml, tiers.exclude", review: "owner" },
  "hazard.acute_toxicity.element": { text: "An element in the policy's acute-toxicity exclusion list.", source: "config/hazard_policy.yaml", review: "owner" },
  "hazard.acute_toxicity.compound": { text: "A compound in the policy's acute-toxicity exclusion list.", source: "config/hazard_policy.yaml", review: "owner" },
  "hazard.acute_toxicity.ghs": { text: "The compound's PubChem GHS record carries an acute-toxicity code the policy excludes.", source: "config/hazard_policy.yaml", review: "owner" },
  "structure.molecular": { text: "A molecular crystal (structural dimensionality 0); layered and network solids are not affected.", source: "docs/SCIENTIST_GUIDE.md, Some things to know: Molecular crystals", review: "owner" },
  "simplicity.max_elements": { text: "More elements than the maximum allowed.", source: "config/scoring_profiles/*.yaml, criteria.simplicity", review: "owner" },
  "simplicity.anion_policy": { text: "The anion does not meet the profile's policy (for example a peroxide under strict oxide).", source: "docs/DECISIONS.md, Strict anion policies", review: "owner" },
  "evidence.tier_min": { text: "The best evidence tier is below the minimum you asked for.", source: "config/schema.py, QuerySettings.evidence_tier_min", review: "owner" },
  "data.no_scorable_criteria": { text: "No criterion has a value, so there is nothing to score.", source: "records/bundle.py, ExclusionRule", review: "owner" },
  "license.non_commercial": { text: "The source record is under a non-commercial license this deployment does not accept; it is dropped at the adapter.", source: "README.md, What goes where", review: "owner" },
  deprecated: { text: "The source has deprecated this entry.", source: "records/bundle.py, ExclusionRule", review: "owner" },
};

export const EVIDENCE_TIER_HELP: Record<string, HelpEntry> = {
  computed_only: { text: "The abstract reports calculations only; nothing was made.", source: "docs/SCIENTIST_GUIDE.md, Evidence tiers", review: "owner" },
  bulk_synthesized: { text: "The abstract reports the material synthesized in bulk.", source: "docs/SCIENTIST_GUIDE.md, Evidence tiers", review: "owner" },
  thin_film_deposited: { text: "The abstract reports the material deposited as a thin film.", source: "docs/SCIENTIST_GUIDE.md, Evidence tiers", review: "owner" },
  dielectric_characterized: { text: "The abstract reports the material characterized for the application (its dielectric properties measured).", source: "docs/SCIENTIST_GUIDE.md, Evidence tiers", review: "owner" },
  not_relevant: { text: "The abstract is about something else.", source: "config/schema.py, CoreConfig.evidence_labels", review: "owner" },
  no_abstract: { text: "The paper has no abstract in OpenAlex, so nothing could be read; this is not the same as no support.", source: "internal plan, OpenAlex sharp edges", review: "owner" },
  unclassified: { text: "Not classified: no model was available, the label was not cached, or the budget was reached. The evidence criterion then carries no weight.", source: "docs/SCIENTIST_GUIDE.md, Evidence tiers", review: "owner" },
};

export function helpFor(kind: "criterion" | "flag" | "caveat" | "exclusion" | "tier", key: string): HelpEntry | undefined {
  const table = {
    criterion: CRITERION_HELP,
    flag: FLAG_HELP,
    caveat: { ...FLAG_HELP, ...CAVEAT_HELP },
    exclusion: EXCLUSION_HELP,
    tier: EVIDENCE_TIER_HELP,
  }[kind];
  return table[key];
}
