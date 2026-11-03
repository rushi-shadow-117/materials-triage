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
