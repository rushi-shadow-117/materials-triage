# Decisions

Each entry: decision, reason, alternative considered. Newest at the bottom.

## 2026-10-31 Keycloak is cut
Decision: no identity provider in Compose. Roles (scientist, site admin, FDE) are first-class
in the API behind a pluggable auth dependency. Dev mode uses static bearer tokens from `.env`.
The README documents how to swap in an OIDC provider.
Reason: the brief asks to describe how each role adjusts settings, not to ship an IdP. Keycloak
costs a container, a seeded realm, OIDC wiring in two codebases, and a cold-run failure mode.
Alternative: Keycloak with a seeded realm and one user per role.

## 2026-10-31 Terraform stays a stretch goal
Decision: `infra/` is reserved. Go/no-go on Nov 13. Compose is the primary deployment.
Reason: cloud infrastructure is not in the brief's hard requirements.
Alternative: cut now and describe deployment in the design note only.

## 2026-10-31 uv manages the Python project
Decision: `uv` with a committed `uv.lock`; `requires-python >= 3.11`, pinned to 3.12 locally.
Reason: one tool for environments, locking, and running; fast; CI uses the same lockfile.
Alternative: pip-tools plus venv.

## 2026-10-31 matminer is not a dependency
Decision: download the matbench_expt_gap file directly from its published URL, pin its SHA256
in `fixtures/snapshots/MANIFEST.json`, and parse it with the standard library.
Reason: matminer pulls a large dependency tree to read one small file.
Alternative: `matminer.datasets.load_dataset("matbench_expt_gap")`.

## 2026-10-31 SiO2 is a reference anchor, not a ranked candidate
Decision: configured incumbents (SiO2 by default) render as labeled comparison rows and are
never ranked. The normal eval expects HfO2, Al2O3, and ZrO2 near the top and SiO2 as an anchor row.
Reason: the overview said both "never ranked" and "expect SiO2 near the top". An anchor row
gives the PI the comparison without the scorer pretending the incumbent is a discovery.
Alternative: rank anchors like any other candidate and mark them.

## 2026-10-31 Numbers come from templates, never from the LLM
Decision: the rationale writer fills text-only slots. The renderer inserts every number from the
provenance bundle. The verifier rejects any digit sequence in an LLM slot that does not resolve
to a bundle value, as a backstop.
Reason: "every number in prose must match a record within rounding" is fragile (years, counts,
"top 5") and makes the LLM the source of numbers in the first place.
Alternative: free prose with a numeric matcher as the primary control.

## 2026-10-31 Experimental band gaps attach to the composition group
Decision: matbench_expt_gap values are composition-level and attach to the polymorph group, with
the row stating that the polymorph is unknown. Zero values are excluded.
Reason: the dataset has no structures. Its zero values are Materials Project DFT metals, not
measurements (arXiv 2501.02932; confirm against the downloaded file in Phase 0).
Alternative: attach the experimental value to the ground-state polymorph.

## 2026-10-31 Hazard policy is element-level first
Decision: the admin-owned hazard policy is tiered by element (exclude, flag, allow), each entry
citing a public source. PubChem GHS data for the compound is a secondary signal. A compound with
no PubChem record is "unknown", lands in the flag tier, scores neutral, and appears in caveats.
Proposed here; confirmed or revised in the Phase 2 round.
Reason: the brief says "non-toxic elements". PubChem maps compounds, not crystal structures, and
most obscure oxides have no record.
Alternative: compound-level GHS as the primary signal.

## 2026-10-31 Formulas, space groups, and oxidation states are template tokens
Decision: the rationale writer's slots are text-only. Formulas, space group numbers, oxidation
states, and all numeric values render through template tokens filled from the bundle. The
verifier first parses formula-shaped tokens in LLM text with pymatgen `Composition` and requires
each to match a bundle composition, then requires any remaining digit sequence to resolve to a
bundle value. Built and tested in Phase 2.
Reason: a plain digit check rejects "HfO2" and "Ta2O5", so every rationale would fail on its
own candidate's name.
Alternative: a digit check with a hand-written allowlist of formulas.

## 2026-10-31 Anchors show a would-rank position
Decision: anchors are scored under the same config as candidates. The renderer shows
"would rank N of M" on the anchor row. Anchors never take a shortlist slot. The eval checks the
scorer against SiO2 through this value. Built in Phase 2.
Reason: the PI needs to see where the incumbent sits; the eval needs a scorer check on SiO2.
Alternative: anchors as unscored comparison rows.

## 2026-10-31 Glossary and search synonyms are separate config
Decision: the glossary (display terminology) lives in the admin-owned site profile. The search
synonym table (which strings query OpenAlex per composition) lives in the FDE-owned versioned
scoring profile. Built in Phase 2.
Reason: one controls wording, the other changes which evidence is found. Merging them lets a
label change silently change results.
Alternative: one glossary used for both.

## 2026-10-31 Roles come only from the token; static tokens need an explicit flag
Decision: the API reads the role from the bearer token and from nothing else. A test proves a
role in a request body, query string, or chat text is ignored. Static-token mode is dev-only;
site mode refuses to start in it unless `ALLOW_STATIC_TOKENS=true` is set. The README says so.
Built in Phase 4.
Reason: with Keycloak cut, this test carries the social-engineering story the SSO demo would have.
Alternative: static tokens allowed in every mode.

## 2026-10-31 Recorded material set widened
Decision: Phase 0 records 11 oxides (HfO2, Al2O3, ZrO2, SiO2, TiO2, ThO2, La2O3, BaTiO3, BeO,
Y2O3, Ta2O5), one discovery-shaped MP query capped at two chunks of 100, and names one
theoretical, one no-dielectric, and one deprecated MP entry in the findings note.
Reason: BeO is the toxicity negative control; Y2O3 and Ta2O5 are known dielectrics for recall;
each later edge case needs a recorded example; pagination and rate limits only appear in bulk.
Alternative: eight oxides, per-formula lookups only.
