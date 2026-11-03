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
| Planted instruction inside a fetched abstract | Treated as data (fixtures/synthetic/openalex_injection.json) | tests/agent/test_classifier.py::test_injected_abstract_is_only_ever_data |

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
| LLM text cites a record id not in the bundle | Sentence removed, `unknown_record_id` logged | tests/verify/test_verifier.py::test_invented_record_id_is_caught |
| LLM text states a number the bundle does not hold | Sentence removed, `unresolved_number` logged | tests/verify/test_verifier.py::test_wrong_number_is_caught |
| Number hidden in a formula-like token (Hf2O5, HfO2.5) | Sentence removed, `formula_not_in_bundle` | tests/verify/test_verifier.py::test_number_hidden_in_a_formula_like_token_is_caught |
| Evidence quote paraphrased | Hit kept with verified=false, `quote_mismatch`, dropped from the PI view | tests/verify/test_verifier.py::test_paraphrased_quote_is_dropped_and_verbatim_quote_passes |
| Evidence quote empty | Rejected as `empty quote` | tests/verify/test_verifier.py::test_quote_check_is_exact_substring_and_rejects_empty |
| Fulltext-scope hit labeled above computed_only | Capped at computed_only, never verified | tests/verify/test_verifier.py::test_fulltext_hit_is_never_verified_and_never_above_computed_only |
| GHS code cited that the bundle does not report | Sentence removed | tests/verify/test_verifier.py::test_ghs_codes_are_accepted_only_when_the_bundle_reports_them |
| Renderer emits a string the verifier would reject | Cannot happen: one precision table | tests/verify/test_verifier.py::test_renderer_output_round_trips_through_the_verifier |
| Planted instruction inside a fetched abstract | Reaches the model only inside the data block; stored only as a verbatim quote; ranks unchanged | tests/agent/test_classifier.py::test_injected_abstract_is_only_ever_data |
| Model replies with text instead of a tool call | Nudged once, then the step fails | tests/agent/test_loop.py::test_no_tool_call_is_nudged_once_then_fails |
| Model calls a tool that is not offered | Treated as no tool call | tests/agent/test_loop.py::test_wrong_tool_name_counts_as_no_tool_call |
| Model stop reason refusal or context overflow | Step fails without retry | tests/agent/test_loop.py::test_refusal_and_context_exceeded_fail_without_retry |
| Budget limit reached | Step ends partial before any request; run labeled partial with the reason | tests/agent/test_loop.py::test_budget_breach_ends_the_step_as_partial_before_any_request, tests/agent/test_classifier.py::test_budget_breach_leaves_the_remaining_hits_unclassified_and_marks_partial |
| Out-of-scope request (wetlab, private data, estimates, config change) | Fixed CoreConfig refusal text; nothing fetched; refusal logged | tests/agent/test_parse.py::test_out_of_scope_request_gets_the_fixed_refusal_text, tests/cli/test_cli.py::test_query_with_a_fake_llm_parses_refuses_and_logs |
| Required field missing from the request | Asked on the terminal; `--yes` refuses to guess | tests/agent/test_parse.py::test_candidate_list_mode_without_formulas_is_missing_required, tests/cli/test_cli.py::test_query_with_a_fake_llm_asks_for_missing_candidates |
| Too few candidates pass | Code enumerates relaxations with exact values and counts; never applied without approval | tests/agent/test_relaxation.py::test_model_picks_by_id_and_may_not_write_digits |
| Model writes digits into a relaxation explanation | Rejected as a tool error | tests/agent/test_relaxation.py::test_model_picks_by_id_and_may_not_write_digits |
| Model writes a slot id that was not requested | Dropped with a log entry | tests/agent/test_rationale.py::test_model_slots_replace_template_text_and_extras_are_dropped |
| Rationale prompt or verbosity changes | Classifier cache key unchanged | tests/agent/test_prompts.py::test_rationale_settings_do_not_change_the_classify_hash |
| Same settings, second run | Byte-identical prompts and hashes | tests/agent/test_prompts.py::test_same_settings_give_identical_prompts_and_hashes |
| Caveat id with no entered text | Visible "caveat text not entered" marker | tests/render/test_markdown.py::test_caveat_resolver_uses_entered_config_text_and_marks_the_rest |
| Bundle from an LLM run rendered before verification | Refused | tests/render/test_markdown.py::test_unverified_llm_bundle_is_refused |
| Glossary applied in technical terminology | Not applied | tests/render/test_markdown.py::test_glossary_applies_only_in_general_terminology |
| Upstream source missing during a run | Availability event; run labeled partial; data stays missing | tests/agent/test_pipeline.py::test_missing_sources_become_events_and_a_partial_run |
| Discovery matches more than the ceiling | Refused with the count; no candidates | tests/agent/test_discovery.py::test_discovery_above_the_ceiling_is_refused_with_the_count |
| Hazard policy edited between runs | Diff attributes to config through the policy hash | tests/cli/test_diff.py::test_hazard_policy_edit_counts_as_config |
| Model changed but no evidence label changed | Diff notes "not causal" | tests/cli/test_diff.py::test_model_change_is_causal_only_through_labels |
| User answers n at the confirmation | Nothing runs, nothing saved | tests/cli/test_cli.py::test_query_prints_criteria_and_an_n_answer_aborts_without_a_run |
| More than five abstracts for one candidate | Only the first five by search order are classified | tests/agent/test_pipeline.py::test_at_most_five_abstracts_per_candidate_are_classified_in_search_order |
| One step exhausts its budget | That step ends partial; the other steps keep their own limits | tests/agent/test_loop.py::test_budget_counts_requests_and_tokens_and_seconds |
| Evidence labeled not_relevant or no_abstract without a sentence | No quote check; stored unverified, no failure | tests/verify/test_verifier.py::test_not_relevant_and_no_abstract_skip_the_quote_check |
| Evidence tier label without a verbatim sentence | `quote_mismatch`, hit dropped | tests/verify/test_verifier.py::test_the_four_tiers_always_need_a_verbatim_sentence |
| Enrichment excludes a top-K row and admits an unenriched one | Loop enriches the newcomer and scores again until the top K is enriched | tests/agent/test_discovery.py::test_recorded_discovery_queries_run_offline_end_to_end_with_the_real_scorer |
| Discovery query without a gap bound | Floor from the profile (hard minimum, else soft preference start) | tests/agent/test_discovery.py::test_discovery_filter_keeps_the_cutoff_out_of_the_api_query |

## Track C: API and web

| Failure | Behavior | Test |
|---|---|---|

## Track D: deploy and docs

| Failure | Behavior | Test |
|---|---|---|

## Track E: eval and validation

| Failure | Behavior | Test |
|---|---|---|
