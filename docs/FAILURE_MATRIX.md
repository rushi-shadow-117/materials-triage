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
