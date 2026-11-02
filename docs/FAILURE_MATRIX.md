# Failure matrix

What can go wrong, what the system does, and the test that proves it. Each track appends
rows only under its own heading. Rows name a test path; a row without a test is a gap.

| Failure | Behavior | Test |
|---|---|---|

## Track 0: data and contracts

| Failure | Behavior | Test |
|---|---|---|
| Upstream returns a credential-free body that is identical to a stored one | One raw row, a new fetch event | tests/provenance/test_store.py::test_same_body_twice_is_one_raw_row_and_two_fetch_events |
| App role attempts UPDATE, DELETE, or DDL | Refused by Postgres | tests/provenance/test_store.py::test_app_role_cannot_update_delete_or_run_ddl |
| Replay mode has no stored response for a call | Missing data, never a network call | tests/adapters/test_runner.py::test_replay_mode_never_calls_the_transport |
| Materials Project database version changes | Cached MP entries invalidated | tests/adapters/test_runner.py::test_version_change_invalidates_mp_cache |
| Upstream unreachable (connect timeout, 5xx) | Retries, then an availability event; run labeled partial | tests/adapters/test_runner.py::test_transport_failure_becomes_an_availability_event |
| Source returns "na" or omits a field | None with a missing reason; never zero | tests/adapters/test_jarvis.py::test_na_sentinel_is_missing_and_zero_stays_zero, tests/adapters/test_mp.py::test_absent_field_is_missing_not_zero |
| Discovery matches more than the ceiling | Refused with the count; agent asks the PI to narrow | tests/adapters/test_mp.py::test_discovery_refuses_above_ceiling |
| GNoME-derived (BY-NC) document appears | Excluded with the license rule | tests/adapters/test_mp.py::test_synthetic_gnome_entry_is_excluded_by_license |
| Deprecated MP entry appears | Excluded with the rule | tests/adapters/test_mp.py::test_synthetic_deprecated_entry_is_excluded_with_rule |
| Functionals disagree on hull status | Flagged, all values kept | tests/adapters/test_mp.py::test_ta2o5_functionals_disagree_on_hull_status |
| Lowest-hull polymorph is theoretical | Flagged; lowest observed polymorph named | tests/adapters/test_groups.py::test_theoretical_ground_state_is_flagged_and_observed_alternative_named |
| PubChem record carries codes but no notifier counts | Codes kept, counts None, never a verdict | tests/adapters/test_pubchem.py::test_hgo_codes_without_aggregate_counts |
| Query setting outside site bounds | Clamped and reported | tests/test_config_schema.py::test_precedence_and_clamping_reports_every_clamp |
| Credential appears in a recorded request | Test fails | tests/test_fixtures_clean.py::test_no_credential_request_headers |
| Planted instruction inside a fetched abstract | Treated as data (Track B tests against fixtures/synthetic/openalex_injection.json) | pending Track B |

## Track A: scoring

| Failure | Behavior | Test |
|---|---|---|
| A weighted criterion rests on a config entry that is not `entered` | Loading the profile fails naming the entry | tests/scoring/test_profile_loader.py::test_weight_on_a_pending_entry_raises |
| Hull energy is exactly 0.0 | Stability scores 1.0, never treated as missing | tests/scoring/test_criteria_properties.py::test_stability_edges, tests/scoring/test_scorer.py::test_baseline_ranking_exclusions_and_anchor |
| Hull energy above the cutoff | Excluded with `stability.cutoff` and the config path | tests/scoring/test_criteria_properties.py::test_stability_is_monotone_non_increasing_and_bounded |
| Band gap missing from every source | Criterion missing with a reason, contribution 0, never 0 eV | tests/scoring/test_band_gap.py::test_missing_gap_is_missing_never_zero |
| Experimental and TBmBJ gaps disagree beyond the tolerance | `band_gap_conflict` flag; fallback source used | tests/scoring/test_band_gap.py::test_tho2_conflict_fires_under_a_test_tolerance_and_falls_to_tbmbj |
| Conflict tolerance not configured | Both values shown, flagged uncompared, no silent choice | tests/scoring/test_band_gap.py::test_no_tolerance_means_shown_but_not_compared |
| Query asks for a looser band gap window than the profile | Profile value kept, note on the row | tests/scoring/test_band_gap.py::test_hard_window_uses_the_stricter_of_profile_and_query |
| Radioactive or IARC Group 1 element present | Excluded with the rule and config path | tests/scoring/test_hazard.py::test_element_rules_exclude_with_their_source |
| Cd or Pb in a Yim 2015 positive | Excluded by the element or acute tier | tests/scoring/test_hazard.py::test_cd_and_pb_yim_entries_are_excluded |
| PubChem has no record for the compound | Unknown tier, neutral score, never allow | tests/scoring/test_hazard.py::test_no_record_is_unknown_and_not_fetched_is_missing |
| Hazard record never fetched (summary pass) | Missing, element rules still apply | tests/scoring/test_hazard.py::test_no_record_is_unknown_and_not_fetched_is_missing |
| GHS codes present outside the acute sets | Flag tier, codes shown as M of N | tests/scoring/test_hazard.py::test_allow_flag_and_unknown_scores |
| Oxyhalide under the strict oxide policy | Excluded with `simplicity.anion_policy` | tests/scoring/test_criteria_properties.py::test_simplicity_rules |
| PI names a polymorph above the cutoff | Scored as named and excluded visibly; other rules logged | tests/scoring/test_scorer.py::test_rocksalt_beo_requested_is_excluded_by_hull_once_be_is_allowed |
| Candidates arrive in a different order | Identical ranks, totals, and serialized rows | tests/scoring/test_scorer.py::test_ranking_is_deterministic_and_order_independent |
| Group has only summary-level data | Scores with missing criteria, weights renormalize, `enrichment_missing` flag | tests/scoring/test_scorer.py::test_summary_level_groups_score_with_missing_enrichment |
| Anchor would outrank candidates | Shown as would-rank N of M, never takes a slot | tests/scoring/test_scorer.py::test_baseline_ranking_exclusions_and_anchor |
| Golden bundle drifts from code or config | Byte comparison fails naming the rebuild command | tests/scoring/test_golden_bundle.py::test_scored_bundle_is_current_and_well_formed |

## Track B: agent, verifier, renderers, CLI

| Failure | Behavior | Test |
|---|---|---|

## Track C: API and web

| Failure | Behavior | Test |
|---|---|---|

## Track D: deploy and docs

| Failure | Behavior | Test |
|---|---|---|

## Track E: eval and validation

| Failure | Behavior | Test |
|---|---|---|
