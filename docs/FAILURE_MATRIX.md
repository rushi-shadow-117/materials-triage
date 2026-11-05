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
| A candidate is excluded by one rule | Every other criterion is still computed and shown; only the excluding criterion is marked "excluded by <rule>" | tests/scoring/test_scorer.py::test_excluded_rows_carry_the_full_breakdown |
| Scientist sets the hazard weight below the site floor | Clamped to 0.1 and the clamp is reported | tests/scoring/test_profile_loader.py::test_site_hazard_weight_floor_clamps_and_is_reported |
| Anion policy is not strict oxide | Every row carries `stability_cutoff_oxide_calibrated` with the profile text | tests/scoring/test_scorer.py::test_non_oxide_anion_policy_emits_the_calibration_caveat |

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
| Discovery query without a gap bound | Floor from the profile (hard minimum, else soft preference start) | tests/agent/test_discovery.py::test_discovery_filter_sends_only_hard_rules_at_their_loosest_value |

## Track E: eval and validation

| Failure | Behavior | Test |
|---|---|---|
| Yim fixture column carries the wrong quantity | Test fails; values nulled with an erratum | tests/evals/test_yim.py::test_no_gap_duplicates_the_space_group |
| Spearman on fewer than two pairs or constant ranks | None with the reason, never a number | tests/evals/test_spearman.py::test_degenerate_inputs_are_none_with_a_reason |
| Composition excluded by the scorer during validation | Listed with its rule, not dropped from the table | tests/evals/test_metrics.py::test_excluded_compositions_are_listed_with_their_rule_not_dropped |
| Composition with no abstract in the literature search | Stays ranked, listed under evidence tier "no abstract" with its sub-state | tests/evals/test_metrics.py::test_no_abstract_rows_stay_ranked_and_are_listed_separately |
| A negative (Be, Cd, Pb) is ranked without a hazard flag | Reported as ranked_unflagged; controls not all handled | tests/evals/test_metrics.py::test_negative_outcomes_cover_every_state |
| Group with no observed polymorph is ranked silently | Controls not all handled unless flagged or excluded | tests/evals/test_metrics.py::test_theoretical_only_groups_must_be_flagged_or_excluded |
| Validation loader needs the network | vcr mode none raises; unknown composition is a KeyError | tests/evals/test_groups.py::test_unknown_key_is_an_error_not_a_fetch |
| A check is planted a violation (wrong rank, missing rule, changed config, disclosed text, echoed injection, stray digit) | The named check fails with the detail | tests/evals/test_checks.py::test_planted_violations_fail_with_a_reason, tests/evals/test_checks.py::test_adversarial_checks_fail_when_the_system_misbehaves |
| Missing value filled in by a score | no_estimated_values fails naming the criterion | tests/evals/test_checks.py::test_planted_violations_fail_with_a_reason |
| Case file names an unknown check or bad params | Check result "unknown check" or "bad params", never a crash | tests/evals/test_checks.py::test_no_bundle_and_unknown_checks_fail_cleanly |
| Adversarial case without an OWASP tag or defenses | Case file rejected at load | tests/evals/test_cases_and_runner.py::test_case_file_rules |
| Required pair not first in a listing | Loader reorders: A1, F1, then id order | tests/evals/test_cases_and_runner.py::test_required_pair_leads_every_listing |
| Executor crashes on a repeat | Repeat recorded as failed with the error, suite continues | evals/runner.py::run_repeat (exercised by the F1 refusal path in tests/evals/test_cases_and_runner.py::test_runner_repeats_and_writes_stable_json) |
| Fake LLM asked to estimate, disclose, change config, or do wetlab work | Fixed core refusal text; no digits in any reply | tests/evals/test_cases_and_runner.py::test_fake_llm_refuses_with_the_core_text_and_never_writes_digits |
| Judge declines a request | Verdict judge_declined, shown in the report | evals/judge.py::AnthropicJudge.judge (fake path: tests/evals/test_judge_and_prereg.py::test_judge_sample_round_trips_to_an_agreement_rate) |
| Scoring config tuned after pre-registration | Report shows both shas and the changed files | tests/evals/test_judge_and_prereg.py::test_preregistration_records_and_compares |
| Results file missing when the report is generated | Report says what is missing; nothing invented | tests/evals/test_generate_eval_report.py::test_report_says_what_is_missing_when_nothing_ran |
| Report regenerated on the same inputs | Byte-identical | tests/evals/test_generate_eval_report.py::test_report_is_built_from_results_and_is_byte_stable |
| Yim-like weight overrides leak into the default run or the profile file | Default run keeps the file's weights and sha; the Yim-like run has its own sha, run id and note | tests/evals/test_track_a_wiring.py::test_yim_like_run_reports_beside_the_default_without_changing_the_profile |
| Yim-like run absent (scorer takes no overrides) | Report prints "not run" in the Yim-like columns, never a number | tests/evals/test_generate_eval_report.py::test_report_is_built_from_results_and_is_byte_stable |
| Case run through the pipeline; the model refuses at parse | Empty bundle in mode `refused`, the fixed refusal text in the transcript, config shas unchanged, a `refused` log entry | tests/evals/test_pipeline_executor.py::test_required_pair_runs_end_to_end |
| Injected abstract with a planted instruction | Served only for the named composition; classified as data; ranks follow scores; the fragment is never echoed outside a verbatim quote | tests/evals/test_pipeline_executor.py::test_injected_abstract_is_data_not_instruction |
| Same case run twice | Same ranks, exclusions and rationale text; different run ids | tests/evals/test_pipeline_executor.py::test_repeats_are_byte_identical_in_what_matters |
| Request names no candidates in candidate-list mode | Filled from the case file when it has them, as the terminal confirmation would; otherwise an error observation, no run | tests/evals/test_pipeline_executor.py::test_missing_candidates_are_filled_from_the_case_or_reported |
| Core tool-call budget spent on classification | Run marked partial with the reason; `run_completed` fails and names it | tests/evals/test_pipeline_executor.py::test_required_pair_runs_end_to_end |
| Scripted model asked to classify or write rationale | Supporting sentence is a verbatim slice of the abstract; rationale text carries tokens only and no digits | tests/evals/test_pipeline_executor.py::test_scripted_model_answers_are_verbatim_and_digit_free |
| Yim row's structure not in our records, or its polymorph lacks a PBE gap or e_total | Listed as unpaired with the reason and the MP id when one matched; left out of the data-level rho; never filled | tests/evals/test_data_level.py::test_every_row_is_paired_by_structure_or_listed |
| Yim row paired to a polymorph | By ICSD id first, else reduced composition and space group number; the PBE gap and e_total are read from that polymorph; experimental median shown separately | tests/evals/test_data_level.py::test_match_order_icsd_then_composition_spacegroup |
| Case the harness cannot run (console action, two-run diff, missing profile) | Reported as skipped with the case file's reason; no pass rate invented | evals/runner.py::run_case (skip_reason) |
| Parse asks for fields the request and case do not give | A clarification outcome, not an error: no run, `clarification_requested` passes, no discovery query | tests/evals/test_pipeline_executor.py::test_missing_candidates_are_filled_from_the_case_or_reported |
| Catalogue expectation with no matching query setting (per-run anchor, hull cutoff, glossary term) | The nearest check is listed and its miss is reported with the detail | tests/evals/test_checks.py::test_new_shape_checks_fail_with_a_reason |
| Repeated run differs in ranks, exclusions or prompt hash | `repeats_identical` false in the results and the report | evals/runner.py::_signature |

## Track F: fixes from the eval run

| Failure | Behavior | Test |
|---|---|---|
| A soft preference or a tighter query setting reaches the discovery API | Only hard rules at their loosest admissible value are sent | tests/agent/test_discovery.py::test_discovery_filter_sends_only_hard_rules_at_their_loosest_value |
| Scientist asks for a hull cutoff outside site bounds | Clamped to the bound and the clamp is shown | tests/test_config_schema.py::test_query_hull_cutoff_is_clamped_to_the_site_bounds |
| Hull cutoff of 0 | On-hull rows score 1.0, all others excluded, no division by zero | tests/scoring/test_criteria_properties.py::test_zero_cutoff_scores_the_hull_and_excludes_the_rest |
| A per-run anchor is also a candidate | It keeps its rank and its anchor row shows the same would-rank | tests/scoring/test_scorer.py::test_query_cutoff_and_per_run_anchor |
| A test runs the eval CLI | Results go to a temporary directory, never evals/results | tests/cli/test_cli.py::test_eval_delegates_or_reports_pending |
| Fewer candidates rank than top_n | Every relaxation states the candidates it adds, from re-scoring the fetched groups, or the log says none is admissible | tests/agent/test_relaxation.py::test_every_proposal_adds_the_count_a_rescore_gives |
| A relaxed value admits only rows another rule excludes | The proposal is dropped | tests/agent/test_relaxation.py::test_every_proposal_adds_the_count_a_rescore_gives |
| A hull relaxation would pass the site maximum | Not proposed | tests/agent/test_relaxation.py::test_hull_relaxation_stays_inside_the_site_bounds |
| A candidate name is not a chemical formula | Reported as not found in any source; the rest are ranked | tests/agent/test_parse_unresolved_and_unavailable.py::test_to_query_settings_proceeds_with_the_resolved_names |
| A request names a property no source provides | Carried as unavailable, logged, and stated in both views; no value shown | tests/agent/test_parse_unresolved_and_unavailable.py::test_handler_carries_both_lists_to_the_outcome |
| A config change moves which rows are enriched | The run diff attributes the change to config, not data | tests/cli/test_diff.py::test_cross_checks_fetched_in_one_run_follow_the_config_change |
| Two eval runs differ in data, model, or nothing | diff_causes_only fails naming the row | tests/evals/test_checks_track_f.py::test_diff_causes_only |

## Track G: molecular solids, egress, fetch default, fixes

| Failure | Behavior | Test |
|---|---|---|
| Scored polymorph is a molecular crystal (dimensionality 0) | Excluded by `structure.molecular`, shown after the hazard rules, value and MP record on the row | tests/scoring/test_structure.py::test_dimensionality_zero_excludes_after_the_hazard_rules |
| Structure not fetched or not analysable | Dimensionality missing with a reason; never excludes | tests/scoring/test_structure.py::test_missing_dimensionality_never_excludes |
| Same structure analysed twice | Same dimensionality | tests/scoring/test_structure.py::test_recorded_structures_give_molecular_and_network_dimensionality |
| A call to a host off the allowlist | Refused before sending; nothing reaches the network | tests/adapters/test_egress.py::test_a_host_off_the_list_is_refused_before_sending |
| The LLM client is pointed at another host | The request hook refuses it | tests/adapters/test_egress.py::test_llm_clients_refuse_other_hosts |
| Postgres down on a CLI run | `--fetch auto` uses the cassettes and logs why | tests/cli/test_cli.py::test_auto_fetch_uses_the_store_only_when_postgres_answers |
| An evidence quote fails the verifier | The hit leaves `bundle.evidence`; the verifier record keeps it | tests/verify/test_verifier.py::test_paraphrased_quote_is_dropped_and_verbatim_quote_passes |
| A second pre-registration after tuning | Both entries kept; the report compares against the latest and lists both | tests/evals/test_judge_and_prereg.py::test_preregistration_records_and_compares |

## Track C: API and web

| Failure | Behavior | Test |
|---|---|---|
| No bearer token in static or OIDC mode | 401, audit-logged | tests/api/test_auth.py::test_static_tokens_give_roles_and_nothing_else_does |
| A role claimed in a header, query string, body or request text | Ignored; the token's role applies | tests/api/test_auth.py::test_static_tokens_give_roles_and_nothing_else_does |
| Scientist calls a console route; FDE calls refresh | 403, audit-logged | tests/api/test_auth.py::test_static_tokens_give_roles_and_nothing_else_does |
| Static tokens in site mode without the explicit allow | The app refuses to start | tests/api/test_auth.py::test_site_mode_refuses_static_tokens_unless_allowed |
| Expired, wrong-audience or wrong-issuer JWT | 401 | tests/api/test_auth.py::test_oidc_rejects_expired_wrong_audience_and_wrong_issuer |
| JWT without a known role | 403 | tests/api/test_auth.py::test_oidc_roles_come_from_the_token_claim |
| A route missing from the permission matrix, or a matrix row the app contradicts | The matrix test fails naming it | tests/api/test_permissions.py::test_permission_matrix_matches_the_app |
| Confirm form posts settings outside site bounds | Resolve previews the clamp; the run applies it | tests/api/test_runs_api.py::test_resolve_previews_clamps_and_a_vague_request_is_clarified |
| A discovery request with nothing to search on | 422 with the fields to supply; nothing fetched | tests/api/test_runs_api.py::test_resolve_previews_clamps_and_a_vague_request_is_clarified |
| A name that is not a formula in Rank my list | Reported as not found; the rest ranked (browser) | tests/e2e/test_browser.py::test_rank_my_list_runs_end_to_end |
| The PI view would show a record id | Ids only in the audit view and drill-down | tests/api/test_runs_api.py::test_candidate_list_run_end_to_end |
| No model configured | /parse says so; the form is filled by hand | tests/api/test_runs_api.py::test_parse_is_unavailable_without_a_model |
| A client-side route opened directly | index.html is served; the app routes | tests/e2e/test_browser.py::test_console_by_role |
| Profile YAML with a weight outside the site bounds | Validation error; save disabled | tests/e2e/test_browser.py::test_console_by_role |

## Track D: deploy and docs

| Failure | Behavior | Test |
|---|---|---|
| A guide names a command, script, or path that does not exist | The docs test fails naming it | tests/test_docs.py::test_commands_and_links_in_docs_exist |
| The README grows past 150 lines | The docs test fails | tests/test_docs.py::test_readme_is_short |
| The api image does not build or does not serve /health from recorded data | The CI docker job fails | .github/workflows/ci.yml (docker job) |
| The Terraform module is unformatted or invalid | The CI terraform job fails | .github/workflows/ci.yml (terraform job) |
| A fresh clone cannot install, build, serve, rank, or run an eval case | scripts/cold_run.sh prints FAIL at that step and exits non-zero | scripts/cold_run.sh |

## Track H fixes: the human test session

| Failure | Behavior | Test |
|---|---|---|
| A fresh clone has no key and no database | The run completes from recorded data; health reports `missing_key` and the banner shows | tests/api/test_fresh_defaults.py::test_missing_key_falls_back_and_the_run_completes |
| The provider rejects the key or the account has no credit | One rejected request sets the status; parse falls back to the form and the run completes | tests/api/test_fresh_defaults.py::test_rejected_key_or_no_credit_falls_back |
| A test reaches the model provider | The SDK's request method raises in every test | tests/api/test_fresh_defaults.py::test_tests_cannot_reach_the_provider |
| A result page or Run history is reloaded or shared | The app loads; the API answers only under /api, and an unknown /api path is a JSON 404 | tests/api/test_spa_routes.py; tests/e2e/test_browser.py::test_reloading_a_result_and_run_history_shows_the_page |
| Keycloak or Postgres is unreachable from the host in development | The dev Compose file publishes both on 127.0.0.1; a browser signs in through Keycloak's page | tests/e2e/test_keycloak_browser.py |
| A site service on the internal network gains a host port | The CI docker job fails on the merged site config | .github/workflows/ci.yml (docker job) |
| Experimental gaps from different material forms are pooled | Only the first preferred form with a point value is aggregated; the others are shown, not used | tests/scoring/test_band_gap.py::test_tho2_pool_never_aggregates_across_forms; tests/scoring/test_band_gap.py::test_al2o3_thin_film_uses_its_film_value |
| A PBE-only gap sits between the profile's PBE floor and its hard minimum | Kept, scored, and flagged with the PBE caveat; below the floor or under a scientist's minimum it is excluded | tests/scoring/test_band_gap.py::test_pbe_only_between_floor_and_minimum_is_kept_and_flagged; tests/api/test_runs_api.py::test_gan_under_the_nitride_profile |
| A template rationale names a caveat by its id | The template carries caveat tokens that render as config text; a test checks no id survives | tests/agent/test_rationale.py::test_template_rationale_renders_caveat_text_never_ids |
| Equal totals read as distinct ranks in name order | Tied rows show "1=" with a note; the CSV marks them tied | tests/render/test_markdown.py::test_equal_totals_render_as_tied; tests/e2e/test_browser.py::test_rank_my_list_runs_end_to_end |
| Every row's key caveat is the same profile-wide sentence | The key caveat follows the row-specific priority; profile-wide caveats show once above the table | tests/render/test_markdown.py::test_key_caveat_is_the_most_row_specific_one |
| An anchor's place reads as last when it outscores the last candidate | The count includes the anchor and its neighbours are named | tests/api/test_runs_api.py::test_anchor_placement_reads_correctly |
| A Materials Project value has no link to its page | Every MP record carries the page URL, and older bundles derive it | tests/api/test_runs_api.py::test_every_materials_project_value_links_to_its_page; tests/render/test_markdown.py::test_record_url_links_materials_project_ids_in_older_bundles |
| A typed name, a lowercase formula, or capitals that are not element symbols | Names and case-insensitive formulas match the synonym table; the rest become chips with a reason; nothing fails the whole list | tests/agent/test_parse_unresolved_and_unavailable.py::test_names_and_lowercase_formulas_match_the_synonym_table; tests/api/test_runs_api.py::test_resolve_matches_names_and_reports_the_rest; tests/e2e/test_browser.py::test_names_and_lowercase_match_and_the_rest_become_chips |
| A composition is missing from the recorded data in an offline run | The reason says offline and that live fetching has it, never that the source lacks it | tests/agent/test_pipeline.py::test_missing_sources_become_events_and_a_partial_run |
| A refresh is requested with a blank or whitespace note | 422; the audit log stores only stripped, non-empty notes | tests/api/test_auth.py::test_refresh_notes_are_stripped_and_must_have_text |
| The limits of the screen are below the fold | The cannot-tell-you panel is above the table, inside the first screen | tests/e2e/test_browser.py::test_rank_my_list_runs_end_to_end |
| A peroxide, superoxide, or azide reaches an oxide or nitride profile | Excluded by simplicity.anion_policy: no oxidation-state guess puts every O at -2 or N at -3 | tests/scoring/test_criteria_properties.py::test_strict_anion_policies_need_the_simple_anion_state |

## Track H: usability

| Failure | Behavior | Test |
|---|---|---|
| A request longer than 2,000 characters | 422 with a sentence on parse and run; the web counter turns red and Parse is off | tests/api/test_limits.py::test_a_request_over_the_character_limit_is_refused_with_a_sentence; tests/test_config_limits.py::test_request_limit_is_exact |
| More than 50 candidates | 422 with a sentence on resolve and run; Run stays off | tests/api/test_limits.py::test_a_candidate_list_over_the_limit_is_refused_on_resolve_and_on_run |
| Candidates pasted with semicolons or mixed separators | The API splits them; the browser parses nothing | tests/api/test_limits.py::test_typed_text_is_split_on_commas_semicolons_and_new_lines; tests/e2e/test_browser.py::test_input_limits_chips_and_the_call_estimate |
| `X-Dev-Role` sent in static or OIDC mode | Ignored; the role is the token's and `role_switch` is false | tests/api/test_auth.py::test_dev_role_header_switches_the_role_in_none_mode_only; tests/api/test_auth.py::test_oidc_roles_come_from_the_token_claim; tests/e2e/test_browser.py::test_the_role_switcher_is_absent_with_static_tokens |
| `AUTH_MODE=none` with `SITE_MODE=true` | The API refuses to start | tests/api/test_auth.py::test_site_mode_refuses_no_auth |
| A help guide name outside the allowlist, or a dotted path | 404; no document leaves docs/ | tests/api/test_help.py::test_the_two_guides_are_served_as_markdown_and_nothing_else_is |
| A new flag, caveat, criterion, rule, or tier without help text | tests/test_help_text.py fails naming the key | tests/test_help_text.py::test_every_vocabulary_key_has_a_help_entry |
| A candidate with no computed dielectric constant | Listed under the chart, never plotted at zero | tests/render/test_views.py::test_chart_points_are_the_bundles_values_with_their_records |
| The PI view's chart | No record ids in its points | tests/render/test_views.py::test_pi_view_chart_has_no_record_ids_and_mev_units_apply; tests/api/test_runs_api.py::test_candidate_list_run_end_to_end |
| A preset provider with no key, or with the Claude default model | `MissingSettingError` naming the variable; the app shows the missing-key banner | tests/agent/test_llm.py::test_preset_providers_need_their_own_key_and_an_explicit_model |
| An OpenAI-compatible endpoint answers 401, 403, 402, or a quota 429 | The model status becomes invalid_key or no_credit and the run falls back | tests/agent/test_llm.py::test_http_status_errors_from_a_compatible_endpoint_set_the_model_status |
| The api image is started with no `.env` | Anthropic provider with `missing_key`, recorded data, the help route answers; never `LLM_PROVIDER=none` from the image | .github/workflows/ci.yml (docker job) |
| The status route is polled while the worker writes the run file | The file is written to a temp name and renamed in one step; an in-flight run answers from its state without reading the file | tests/cli/test_run_store_atomic.py; tests/api/test_runs_api.py |
