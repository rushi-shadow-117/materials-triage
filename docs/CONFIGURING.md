# Configuring

Four layers, resolved in code with precedence core > site > profile > query. A query value
outside the site bounds is clamped and the clamp is shown. Unknown keys are rejected.

| Layer | Owner | Where | Holds |
|---|---|---|---|
| Core | code | `src/materials_triage/config/schema.py` (`CoreConfig`) | refusal texts, allowed hosts, per-step model budgets, abstracts per candidate, input limits (2,000 request characters, 50 candidates) |
| Site | admin | `config/site_profile.default.yaml`, `config/hazard_policy.yaml` | weight bounds, hull cutoff bounds, top N max, defaults, glossary, deposition methods, "cannot tell you", ECHA line; the hazard tiers |
| Profile | field engineer | `config/scoring_profiles/*.yaml` | weights, thresholds, band gap policy, discovery floor, anchors, synonyms, structure rule |
| Query | scientist | the confirm form or `--criteria` file | the per-run settings below |

## Entry statuses

Every config entry with a value carries `status`, `source`, `entered_by`, `entered_on`
(`config/README.md` gives the vocabulary). Only `entered` entries are used. A criterion with
weight above zero whose entry is `pending_verification` or `open` makes the profile fail to
load, naming the entry. Pending entries today: the dielectric target band (Robertson 2004
awaits the primary PDF), three reference values, and the cost criterion (no source wired).

## Query settings

| Field | Meaning | Bound |
|---|---|---|
| `mode` | `discovery` or `candidate_list` | |
| `candidate_list` | reduced formulas to rank | at most 50; names that are not formulas are reported as not found |
| `candidate_text`, `extra_anchors_text` | the same lists as typed text; the API splits on commas, semicolons, and new lines | replaced by the list before validation |
| `top_n` | rows shown | 1 to `site.top_n_max` (50) |
| `weights` | per criterion | `site.weight_bounds` (hazard at least 0.1) |
| `band_gap_min_ev`, `band_gap_max_ev` | a hard window; the stricter of profile and query applies | |
| `e_above_hull_max_mev` | the hull cutoff for this run | `site.stability_cutoff_bounds` (0 to 94) |
| `max_elements` | element count limit | |
| `evidence_tier_min` | exclude below this evidence tier | |
| `extra_anchors` | reference rows for this run; they stay ranked | |
| `exclude_radioactive` | locked on by the site | |
| `verbosity`, `terminology`, `units`, `view` | output only; numbers never change | |

## Site profile

- `weight_bounds`: min and max per criterion.
- `stability_cutoff_bounds`: `min_mev_per_atom`, `max_mev_per_atom`; the maximum is also the
  hull limit sent to the discovery query.
- `defaults`: `top_n_max`, `default_view`, `default_verbosity`, `default_terminology`,
  `radioactive_exclusion_locked`.
- `glossary.terms`: display terms applied when terminology is general.
- `deposition_methods.methods`: the site's methods, matched against abstract labels.
- `screen_cannot_tell_you.items`: shown as missing on every row.
- `attribution.echa.text`: the attribution line for rows citing ECHA.

## Hazard policy

`config/hazard_policy.yaml`, applied in this order: radioactive elements (locked),
`exclude` elements (IARC Group 1), acute element tiers, acute compound tiers, GHS codes in the
exclude set (H300, H310, H330, H360); then the flag set (acute flag codes and
`ghs_flag_codes`: H340, H341, H350, H351, H361, H370) at the neutral score with the
`caveat_template` sentence filled from the record; every other code is a process-hazard
caveat at the allow score. A compound with no PubChem record is unknown, scored neutral, never
allowed by default. Each entry cites its source; add a row the same way.

## Scoring profile

Start from `config/scoring_profiles/nitride_wide_gap.yaml`, the smallest one. The sections:

- `criteria.stability`: `cutoff_mev_per_atom`, `near_cutoff_band_mev_per_atom`, the hull key,
  the caveat texts (hull mismatch, oxide calibration for non-oxide anion policies).
- `criteria.band_gap`: `policy` (`best_available` or `pbe_only`), `source_order`,
  `soft_preference_start_ev` or a hard window (`hard_min_ev`, `hard_max_ev`),
  `discovery_prefilter.pbe_floor_ev` (what the discovery query sends),
  `conflict_tolerance_ev`, `on_conflict`, `standing_caveat`.
- `criteria.structure`: `exclude_dimensionality` (`[0]` excludes molecular crystals).
- `criteria.simplicity`: `max_elements`, `anion_policy` (`strict_oxide`, `strict_nitride`,
  `any`), `ternary_penalty`.
- `criteria.evidence.tiers`: the ordinal value per evidence label.
- `criteria.dielectric_constant.target_band`, `criteria.deposition_method`,
  `criteria.cost`: optional criteria at weight 0 unless entered.
- `weights.values`, `sensitivity.perturbation`, `synonyms.terms`, `anchors.compositions`,
  `screen_cannot_tell_you.items` (profile-specific missing markers).

Upload it in the console (validated, saved as a new version) or add the file and open a pull
request. The loader refuses a weighted criterion whose entry is not `entered`, a weight
outside the site bounds fails validation, and the clamp preview shows what a default query
would get. Every profile gets the same scorer; a second profile with the same data and
different thresholds is how the tool is shown to be general.
