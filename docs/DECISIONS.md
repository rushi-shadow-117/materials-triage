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

## 2026-10-31 The expt_gap compendium is the experimental band gap source; matbench is for validation
Decision: the product reads matminer's full `expt_gap` compendium (6,354 rows, pinned SHA256)
and shows the measured range and count per composition. `matbench_expt_gap` is used only to
calibrate in validation. How several values collapse to one number for scoring (median shown
with range, or minimum) is an open decision for the Phase 2 round.
Reason: matbench's deduplication removed every composition whose reported gaps span more than
0.1 eV, which dropped BaTiO3 and ThO2 from our set. The compendium has them with their spread.
Neither table has Al2O3 or SiO2; those fall through to computed gaps and the row says so.
Alternative: matbench alone, one value per composition.

## 2026-10-31 PubChem GHS is never majority-voted to safe
Decision: the hazard row shows "hazard codes in M of N notifications" from the PUG-View
aggregate. A compound with any hazard code in any notification is never shown as unclassified.
The adapter parses the "N of M" counts and stores the raw strings. Built in Phase 1.
Reason: PubChem aggregates company notifications that disagree; most say "Not Classified" while
a minority report codes. Collapsing that to the majority hides the signal.
Alternative: show the majority classification.

## 2026-10-31 Particulate hazard codes become a process-hazard flag
Decision: GHS codes about respirable particulates do not exclude a material and are not
dismissed. They raise a process-hazard flag: keep the candidate, attach a caveat whose text and
source the owner enters in the hazard policy config. Code carries a TODO naming the fact to
source. Built in Phase 2 with the hazard policy loader.
Reason: whether dust codes matter for a given thin-film process is a safety judgment outside
this codebase's authority (CLAUDE.md, Chemistry claims). Thin-film work can involve powders,
targets, and chamber cleaning, so the flag must survive to the PI.
Alternative: treat particulate codes as not applicable to films (rejected; an unsourced
chemistry judgment).

## 2026-10-31 JARVIS to MP matching is ICSD-first with a structural fallback
Decision: parse JARVIS `icsd` (comma-separated string, possibly empty) to a set of IDs and match
when it intersects the ICSD IDs in MP's `database_IDs`. Fall back to reduced composition plus
space group number. Field shape on the MP side is confirmed once a key exists. Built in Phase 1.
Reason: 125 of 205 slice records carry an ICSD ID, so an identifier match is available for most.
Alternative: composition plus space group only.

## 2026-10-31 COD outage handling
Decision: COD stays planned as a core source. Retry daily during Phase 1. If still unreachable
at the end of Phase 1, demote it to optional and rely on MP's `theoretical` flag for the
experimental-existence signal. The outage is logged in docs/wire-findings.md as an availability
event and is the reference case for the health page and labeled partial results.
Reason: one day of unreachability is not evidence about the source; it is evidence that the
product needs availability handling.
Alternative: drop COD now.

## 2026-10-31 Experimental gaps are not automatically best: a conflict rule applies
Decision: when the experimental gap and the TBmBJ gap for a composition group differ by more
than `band_gap.conflict_tolerance_ev` (scoring profile, owner-set), the row shows both values
with their sources and the flag "sources conflict", and the scorer uses the band gap policy's
fallback source instead of the experimental value. A composition with only one source carries
"single source". Whether the fallback on conflict is the next source in policy order (default)
or the minimum of the conflicting values is an open decision for the Phase 2 round. ThO2 is the
planned test case: the compendium slice and the JARVIS slice disagree for it, and the test
asserts only that the flag fires and the fallback is used, under a tolerance set in the test's
own config. No reference value for ThO2 is stated in this repo; the owner sources it.
Reason: the compendium has no per-row references, so a conflicting row cannot be traced.
Surfacing the conflict is honest; silently trusting either side is not.
Alternative: trust the experimental value whenever one exists.

## 2026-10-31 Reference values are config entries with citation and material form
Decision: owner-entered experimental values (first use: SiO2 and Al2O3 band gaps, which no
public gap table in this repo contains) live in `config/reference_values.yaml` with
composition, property, value, `form` (`crystalline_bulk` or `amorphous_film`; extended only
when a sourced entry needs it), `source` (citation, URL, `access: open`), notes, entered_by,
entered_on. They pass through the provenance store like any record (source `config`, record ID
from the entry key plus config version), so invariant 1 holds. The row shows the form beside the
value. Built in Phase 2.
Reason: thin-film dielectrics are often amorphous and the form can change the measured gap, so
a value without its form is ambiguous. The brief allows citing published work.
Alternative: a bare value per composition.

## 2026-10-31 JARVIS adapter rules: "na" is missing, ICSD is a list
Decision: in the JARVIS adapter, the string `"na"` in any field maps to missing, never to 0 or
a default. `spg_number` parses to an int. `icsd` parses from a comma-separated string to a list
of ints; an empty string is an empty list; a non-numeric token is dropped and logged. A record
with a missing gap is excluded from gap-based scoring with the exclusion reason recorded.
Tests for each rule land with the adapter in Phase 1. `parse_icsd` in
`scripts/fetch_snapshots.py` moves into the adapter.
Reason: 42 of 64 fields in the slice use `"na"`, including every gap and dielectric field. A
careless cast turns a missing value into a 0 eV gap that sinks a good candidate.
Alternative: coerce with a default.

## 2026-10-31 Owner-sourced values enter config now, each with a status
Decision: the owner's resolved sourcing queue is written into `config/` as YAML with
`schema_version: 0` before the Phase 2 Pydantic schema exists, so the schema is built around
real entries. Every entry carries `status`, `entered_by`, `entered_on`, and a `source` block
(citation, url, access). Statuses: `entered` (value with a located open source),
`pending_verification` (owner-supplied value whose primary source is not yet located or
checked), `pending_signoff` (owner asked to sign off), `open` (no value yet). The Phase 2
loader uses only `entered`; the rest render as missing with their status shown. A test checks
the structure. Values and relevance judgments are the owner's and are attributed as such.
Reason: entries without a locatable open source must not drive a score; entering them with a
visible status keeps the queue honest without losing the owner's work.
Alternative: hold the values in internal notes until the schema exists.

## 2026-10-31 Hazard policy defaults from the owner's sourcing
Decision (owner): tiers are by hazard type and authority. Carcinogenicity from IARC: exclude
elements whose compounds are IARC Group 1 as a group (arsenic, beryllium, cadmium); chromium is
flagged, not excluded, because only Cr(VI) compounds are Group 1 and the flag names the
oxidation state; nickel defaults to exclude with `pending_signoff` and an admin may downgrade
it to flag. Radiological hazard from nuclear data: exclude elements with no stable isotope
(technetium, promethium, polonium and every heavier element), citing the NNDC chart of
nuclides. Acute toxicity (mercury, thallium, lead, soluble barium) is `open` until GHS acute
toxicity classifications for representative compounds are recorded from PubChem in Phase 1.
Particulate hazards are a process-hazard tier: keep the material and attach the owner's caveat
text with a per-material classification entry.
Reason: "non-toxic" hides three different hazards with three different authorities.
Alternative: one combined toxicity switch.

## 2026-10-31 Scoring defaults from the owner's sourcing
Decision (owner): in the `gate_dielectric_on_si` profile, band gap is a soft preference starting
at 5 eV with a standing caveat that band offsets to the substrate are not checked; dielectric
constant is a 10 to 30 target band at zero weight by default; simplicity is at most 3 elements
with oxygen as the only anion and a ternary penalty (a PI preference, listed as a discovery
question); several experimental gap values aggregate to the median, scored on the median with
the full range shown, minimum offered as the conservative option; anchors default to SiO2 only
(HfO2 is an expected ranked result and is not anchored). The stability threshold is `open`
until the oxide-specific 90th percentile of observed metastability is read from Sun et al.
2016; its planned shape is a soft ramp to that value and a hard cutoff there, with the paper's
24 meV/atom DFT uncertainty noted. The band gap conflict tolerance is not sourced but measured
in Phase 2 as twice the TBmBJ-vs-experimental error on the oxide subset, derivation recorded.
Reason: each is either a sourced recommendation, a measured quantity, or an explicit preference,
never a value chosen by the code's author.
Alternative: fixed literature thresholds without derivation.

## 2026-10-31 Search synonyms come from PubChem, curated by the FDE
Decision: the recorder fetches PubChem's synonyms list for each chosen CID; the FDE-owned
synonym table is curated from that recorded, sourced list down to trivial names (hafnia,
zirconia, alumina, and so on). Recorded for all 11 oxides on 2026-10-31 (28 to 1288 names each).
Reason: deterministic and sourced; the FDE still controls what drives literature search.
Alternative: hand-written synonyms.

## 2026-10-31 Materials Project records keep both ID forms and the thermo type
Decision: the provenance store keeps the raw response body (whose IDs look like `mp-aaaaaayt`)
and its hash; the normalized record carries the client-decoded ID (`mp-643`) and a pointer to
the raw record. Every hull energy is stored with its `thermo_type` from the thermo endpoint;
the summary value is labeled as the mixed `GGA_GGA+U_R2SCAN` hull, which the recording showed
it to be. Built in Phase 1.
Reason: the two ID forms cannot be cross-referenced otherwise, and the functional changes which
polymorph is on the hull (Ta2O5 mp-1539317 is stable in GGA_GGA+U and not in the mixed hull).
Alternative: store the client ID only and the summary hull energy without its functional.

## 2026-10-31 Egress allowlist for Materials Project and OpenAlex comes from the recordings
Decision: `api.materialsproject.org` paths `/materials/summary/`, `/materials/dielectric/`,
`/materials/thermo/`, `/heartbeat`; `api.openalex.org` path `/works`. Nothing else was
contacted during recording, confirmed by an offline replay with no unrecorded request.
Reason: the overview requires the allowlist to be built from observed hosts, not documentation.
Alternative: allow the two hosts wholesale.

## 2026-10-31 Stability threshold: 94 meV/atom from observed binary oxide polymorphs
Decision (owner): the stability score ramps linearly from 1 at 0 meV/atom above the hull to 0
at 94 meV/atom and candidates above 94 meV/atom are excluded; both numbers are configurable.
Rows within 24 meV/atom of the cutoff carry a "near cutoff" flag, and that band is also where
per-functional thermo documents are fetched to check for hull-status disagreement (Phase 1
decision 5 as the owner resolved it).
Reason: Sun et al., Sci. Adv. 2, e1600225 (2016), CC BY-NC 4.0, state that for observed
(ICSD) binary oxide polymorphs "the 90th percentile for binary oxides occurring at 94
meV/atom", and that DFT formation energies relative to adjacent stable compounds are accurate
to about 24 meV/atom. Caveat recorded with the entry: that percentile was computed on
Materials Project GGA/GGA+U (PBE) energies, before the r2SCAN mixed hull that MP's summary
endpoint now reports; the cutoff is applied to the mixed hull as the policy default and the
discrepancy is a known limitation.
Alternative: the all-chemistries 90th percentile of 67 meV/atom.

## 2026-10-31 Acute toxicity rule is compound-level GHS; tiers reported before entry
Decision (owner): GHS hazard statements from PubChem decide the acute toxicity tier of a
compound. H300, H310, H330, or H360 present in any notification: exclude. Any other acute
toxicity statement (H301, H302, H311, H312, H331, H332): flag. Code meanings cite the UN GHS.
Probe compounds HgO, Tl2O3, PbO, BaO, BaTiO3 were recorded on 2026-10-31 and the resulting
tiers reported to the owner; no acute tier entry is written until the owner confirms.
Reason: IARC covers carcinogenicity only; acute poisoning hazards need GHS. Compound-level
data lets BaTiO3 be judged separately from soluble barium compounds.
Alternative: element-level acute toxicity list.

## 2026-10-31 Owner approvals: nickel exclusion and the 5 eV soft gap preference
Decision (owner): nickel defaults to exclude (IARC Group 1, nickel compounds as a group) with
admin downgrade to flag; status entered. The gate-dielectric profile's soft band gap
preference starting at 5 eV, with the standing caveat that band offsets to the substrate are
not checked, is approved as the owner's application choice; status entered. The Robertson
(2004) statements cited in its rationale remain pending verification against the primary PDF,
which no tool-driven fetch could retrieve (HTTP 403 from the publisher; a browser-impersonating
fetch was declined on principle). The owner supplies a local copy for the check.

## 2026-10-31 Scope rule for chemistry; chemistry sourcing is closed
Decision (owner): a chemistry item belongs only if it changes something the brief asks a user
to see: a rank, an exclusion, a caveat, or a missing-data marker. Anything that only makes the
system more scientifically complete is scope. Chemistry sourcing is closed unless a test fails
on it; remaining queue items are verification, not new chemistry. Rejected on this rule, so
they do not resurface: a figure-of-merit criterion (not in the brief, one more default to
defend); a `published_error` field on every value (error figures go in caveat text once, with
citations); a second, stricter stability profile at 20 meV/atom (one cutoff with one source);
extracting a further literature figure for validation (Yim 2015's tables already give positives
and negatives). None of these existed in this repo; recorded to keep them out.
Reason: the brief does not ask for publishable scientific claims. The advantage is software
judgment: every caveat explainable in two sentences with its source named.
Alternative: continue adding criteria as the literature suggests them.

## 2026-10-31 Validation ground truth is an external list
Decision (owner): positives for the validation eval come from Yim et al., Novel high-k
dielectrics for next-generation electronic devices screened by automated ab initio
calculations, NPG Asia Materials 7, e190 (2015), DOI 10.1038/am.2015.57, CC BY 4.0, Tables 1
to 3; negatives are c-BeO, CdTiO3, Cd2Ta2O7, PbHfO3, PbZrO3 (owner's list). Metric: Spearman
rank correlation against the positives, plus every negative excluded or flagged with its rule
shown. Stored in `fixtures/validation/yim2015.yaml` with the table number per row. Used in
Phase 2.
Reason: the eval needs a candidate list the project did not author.
Alternative: hand-picked expectations (HfO2, Al2O3, ZrO2 near the top) only.

## 2026-10-31 Licensing is enforced per source and per record
Decision (owner): the site profile lists each source with its license and a `commercial_ok`
flag; `exclude_non_commercial` is on by default. Materials Project GNoME-derived entries are
CC BY-NC and are controlled in two layers: deployment accounts never accept the GNoME license
(so the API omits them; documented in the admin README), and the adapter excludes any document
whose `builder_meta.license` is `BY-NC`, recording the rule. Wherever PubChem GHS text derives
from ECHA, the row carries the ECHA attribution line. Each record's provenance carries its
license. Source license strings are entered only from the source's own terms page.
Reason: licensing is a brief requirement and a software control, not chemistry. Confirmed from
Materials Project documentation: GNoME entries carry `builder_meta.license = "BY-NC"` and
`builder_meta.batch_id = "gnome_r2scan_statics"`, and are omitted for accounts that have not
accepted the license; our probe for a GNoME ID returned no document, consistent with that.
Alternative: allow all MP data and rely on users to check licenses.

## 2026-10-31 Deployment and eval additions recorded for later phases
Decision (owner): Phase 4 adds an Apptainer recipe beside Compose, a no-LLM mode (structured
criteria form, evidence tier "unclassified", template-only rationale), and an OpenAI-compatible
endpoint option for self-hosted models. Phase 3 tags each adversarial eval case with an OWASP
LLM Top 10 (2025) category and reports task completion and attack success per case.
Reason: deployment portability and a recognizable threat taxonomy are software judgment the
reviewer can check.

## 2026-10-31 Phase 1 decisions
Decision (owner, applied to the Phase 1 plan):
1. Materials Project is called directly over REST with httpx; raw IDs are decoded with the
   base-26 AlphaID scheme from `emmet.core.mpid` (the encoding's source); every recorded
   (raw, client) ID pair is a test. `mp-api` is a dev dependency for cross-checks only.
2. Alembic manages the schema from the first migration.
3. Discovery never truncates: pages of 1,000 up to a hard ceiling of 10,000; above it the
   adapter refuses, reports the count, and the agent asks the PI to narrow.
4. Cache TTLs: MP 7 days, OpenAlex 30, PubChem 90, OPTIMADE 30; snapshots none. MP entries are
   invalidated on a database version change (from `/heartbeat`, once per run). Refresh is a
   logged admin-only endpoint that appends and never overwrites.
5. Thermo documents are fetched for an explicit, caller-supplied ID list (all polymorphs of the
   named compositions); Phase 2 passes top-K plus compositions in the near-cutoff band.
6. OpenAlex default scope is `search.title_and_abstract`; fulltext is an FDE option whose hits
   are labeled unverifiable by the quote check; the unfiltered match count is recorded beside
   the abstract-filtered results.
7. OQMD is cut from Phase 1 and listed as a documented extension; its cassettes remain as
   fixtures for the provider-agnostic OPTIMADE parser. COD is the only wired OPTIMADE provider.
8. Three Postgres roles from day one: `triage_app` (INSERT, SELECT), `triage_migrate` (DDL,
   Alembic), `triage_maint` (DELETE for retention via a logged admin job).
Reason: each is recorded with its trade-off in internal/PHASE1_PLAN.md.

## 2026-10-31 GNoME gating confirmed on the wire
Decision: no change; the licensing decision stands with evidence. The `/heartbeat` response
lists `access_controlled_batch_ids: ["gnome_r2scan_statics"]`, and every summary document this
account received carries `builder_meta.license = "BY-C"`. The adapter's `BY-NC` exclusion is
tested on a synthetic document because no real one can be fetched by an account that has not
accepted the GNoME license, which is the deployment rule.

## 2026-10-31 Acute toxicity tiers entered; thallium excluded at element level
Decision (owner): from the recorded PubChem probes, HgO and PbO are excluded, BaO is flagged,
BaTiO3 is unknown and ends up flagged through the element-level barium flag. Thallium gets an
element-level exclude because thallium metal (CID 5359464) carries H300, H310, H330 and
thallium(I) sulfate (CID 24833) carries H300, while Tl2O3 itself has no GHS data. Hg and Pb
are also excluded at element level from the same records.
Reason: the compound-level rule alone misses elements whose common oxides have no GHS
record; a representative compound with fatal acute toxicity codes is the owner's test.
Alternative: keep thallium at flag with "no record".

## 2026-10-31 Several experimental values per composition are kept, never reconciled by hand
Decision (owner): when two good sources differ slightly (Al2O3 crystalline, 8.7 eV in one and
8.8 eV in another), both are entered with their citations and the row shows the range and the
source count. The aggregate rule (median shown with range) applies to reference values exactly
as it does to the compendium.
Reason: picking one would be an unsourced judgment; the spread is real information.
Alternative: pick the more recent or the more cited value.

## 2026-10-31 Source URL corrections from verification
Decision: entries are flipped to entered only when the page at the URL states the value. The
ThO2 photoemission source (Kelly et al., Phys. Status Solidi RRL 2014) states "6 eV to 7 eV,
from UPS and IPES" and is entered. The owner's NSF PAR record 10427156 for the ALD SiO2 8.7 eV
value resolves to an unrelated paper; the 8.7 eV statement on that page belongs to a 2021
band-offset paper that uses it as an input, so the entry stays pending until the owner confirms
the intended record. The 7.0 and 7.6 eV Al2O3 values are dropped (no primary source). The
arXiv 1705.00315 abstract does not state 6.6 eV; the body text is checked before entry.
Reason: a citation that does not contain the value is not a source.

## 2026-11-02 Track 0: data and contracts
Decision (owner's parallel plan): Track 0 records the full composition set, ships the bundle
and config contracts, a generated sample bundle, CLI and API stubs with generated TypeScript
types, and freezes dependencies. After it merges, pyproject.toml, uv.lock, CLAUDE.md,
internal/PLAN_OVERVIEW.md, records/, provenance/, and adapters/ are frozen; a track that
needs a change there stops and asks. Each later track appends only under its own heading
below. Rules: internal/parallel-plan.md.
Reason: six sessions build in parallel against one deadline; collisions cost more than the
contracts cost.
Alternative: one sequential session.

## Track A: scoring

### 2026-11-02 The bundle carries a polymorph summary; the store keeps the list
Decision (owner): `Candidate.group` and `Anchor.group` are a `CompositionSummary`: a
`PolymorphSummary` (ground state, lowest observed, the scored polymorph, observed, theoretical
and unknown counts, the five lowest polymorphs by mixed-hull energy, each row with its
provenance and any polymorph-level exclusion rule) plus the composition-level experimental
gaps, reference values, hazard record, and literature result. The full polymorph list stays in
the provenance store and is referenced by `composition_id`, the pymatgen reduced formula that
is the `composition` column of `triage.records`
(`Store.records_for(source="materials_project", kind="mp_summary", composition=id)`).
`CompositionGroup` remains the in-memory object the scorer reads. `BUNDLE_VERSION` is 2.
Reason: the sample bundle with full groups was 3.5 MB for eleven oxides, mostly provenance
repeated per polymorph; the user-facing views need the ground state, the observed alternative,
and a short list. The store already holds every record.
Alternative: full groups in the bundle (Track 0 sample), or ids only with no rows.

### 2026-11-02 Exclusion rules, flags, and caveat ids are closed vocabularies
Decision: `ExclusionRule`, `Flag`, and `CaveatId` enums in `records/bundle.py` name every
value the scorer can emit; `Exclusion.rule`, `Candidate.flags`, and `Caveat.id` are typed on
them, and a `Caveat` carries a `subject` (element or composition) and the config entry that
holds its text. `CriterionScore.provenance` carries the record each scored number came from,
since the full group is no longer in the bundle.
Reason: Track B resolves text against these ids; a free string would let a typo become a
silent missing caveat.
Alternative: free strings with a shared constants module.

### 2026-11-02 Default profile renamed; optional criteria added to CRITERIA
Decision (owner): `config/scoring_profiles/oxide_dielectric_thin_film.yaml` replaces
`gate_dielectric_on_si.yaml` (same owner-sourced entries; `default_paths()`, the API stub, and
the CLI default repointed). `CRITERIA` in `config/schema.py` gains `deposition_method` and
`cost`, both weight 0 by default (`OPTIONAL_CRITERIA`), so site weight bounds and query
clamping govern them like the other criteria. The owner approved these two frozen-file edits
on 2026-11-02 as part of the Track A contract commit.
Reason: the profile name describes the use case the brief states; optional criteria that
cannot be weighted through `resolve()` would need a second configuration path.
Alternative: a separate `config/profiles/` directory; optional criteria outside `resolve()`.

### 2026-11-02 Store tests skip without Postgres
Decision: the autouse table-cleanup fixture in `tests/conftest.py` does nothing when Postgres
is unreachable, so store and replay tests skip through `requires_db` instead of every test
erroring in cleanup.
Reason: parallel tracks run the suite in worktrees that may not have Compose up.

### 2026-11-02 Scoring rules (Track A)
Decision: the scorer in `src/materials_triage/scoring/` applies these rules; each is a design
choice recorded here, none is a chemistry claim.
- Total: weighted mean over criteria that have a value (`sum(normalized * weight) /
  sum(weight)` over present criteria). A missing criterion contributes nothing and is listed
  with its reason; weights renormalize. A candidate with no present weighted criterion is
  excluded with `data.no_scorable_criteria`. Alternative: divide by all weights, which would
  score missing data as zero.
- Rank key: `(-total, composition, scored MP id)`. When several rules exclude a candidate the
  first in a fixed order (hazard, stability, band gap, simplicity, evidence, data) is shown and
  the rest go in the decision log under `also_excluded_by`.
- Stability: `1 - hull_mev / cutoff` clamped to 0..1; above the cutoff excluded; within the
  near-cutoff band on either side flagged. Alternative: a step at the cutoff.
- Band gap: the experimental pool is the compendium plus entered reference values; point
  values form the median (minimum as the option), ranges widen the shown range and count as
  sources but do not enter the aggregate. TBmBJ is the JARVIS value matched onto the scored
  polymorph; PBE is its MP summary gap. Conflict is checked only when
  `conflict_tolerance_ev` is set; otherwise the row is flagged `band_gap_sources_uncompared`
  and both values are shown. The tolerance stays `open` until Track E derives it (twice the
  TBmBJ-vs-experimental error on the oxide subset). The hard window is the stricter of the
  profile's and the query's; a looser query value is logged and ignored. Normalized:
  `min(1, gap / soft_preference_start_ev)`; 1.0 inside a pure window. Alternative: trust the
  experimental value whenever present (rejected 2026-10-31).
- Hazard: element rules exclude first (radioactive, exclude tier, acute element tier), then
  the compound tier, then GHS codes in the acute exclude set. Otherwise `flag` when an element
  or compound flag applies, any GHS code is present, a process-hazard classification applies,
  or no PubChem record exists (unknown); `allow` only with a record, no code, and no flag.
  Scores: allow 1.0, flag and unknown 0.5. A record never fetched is missing, not unknown.
  Superseded in part by the owner's GHS code decision below.
- Process hazard: fires only on the policy's per-material classifications (SiO2, TiO2). The
  particulate GHS code list is unsourced; a TODO in `scoring/hazard.py` names it.
- Simplicity: element count above `max_elements` excludes; anions are the elements with a
  negative state in pymatgen's first oxidation-state guess, and `strict_oxide` requires O as
  the only anion (so hydroxides pass, oxyhalides do not); no guess flags, never excludes.
  Binary 1.0; ternary `1 - ternary_penalty_size` when entered else
  `(max_elements + 1 - n) / (max_elements - 1)` (0.5 at max 3). Alternative: a configured
  anion element list, which would be a chemistry claim without a source.
- Evidence: ordinal tier of the best verified label (owner decision 2026-11-02); no label is
  missing with reason `unclassified`. `evidence_tier_min` excludes a classified candidate
  below it and only flags an unclassified one.
- Dielectric constant: 1.0 inside the target band, linear decay to 0 one band width outside;
  the loader refuses weight above 0 while the band is pending.
- Sensitivity: each weighted criterion rescored at x0.8 and x1.2 one at a time; perturbed
  weights are not clamped by site bounds (an analysis, not a setting).
- Polymorph: the ground state is scored unless the PI names an MP id, which is scored as given
  so the stability rule can exclude it visibly (`polymorph_requested` flag).
- Thermo enrichment ids: every MP id of compositions ranked in the top K or whose scored hull
  is within the near-cutoff band of the cutoff on either side.
- Summary-level groups (discovery before enrichment) score with hazard, dielectric, TBmBJ,
  and evidence missing and the row flagged `enrichment_missing`; composition-level tables
  still apply.
- Golden fixture `fixtures/bundles/scored_bundle.json`: replayed responses carry the fixture
  time (2026-11-02T12:00Z) instead of the wall clock so the file is byte-identical per build.
Reason: every number a user sees must come from a rule that can be stated in two sentences
with its source; these are those rules.

### 2026-11-02 GHS codes outside the exclude sets: flag set and process-hazard caveat
Decision (owner policy decision, taken on seeing the Al2O3 result in the first scoring pass,
before pre-registration): GHS codes outside the acute exclude set map in two ways. A flag set
(admin-configurable, default H340, H341, H350, H351, H361, H370, entered in
`config/hazard_policy.yaml#tiers.ghs_flag_codes`) keeps the candidate ranked at the neutral
0.5 with the flag shown, alongside the acute flag codes. Every other code (H315, H319, H335,
H372, H373, and so on) becomes a process-hazard caveat and the candidate keeps the allow score
of 1.0, with the codes shown as M of N notifications. Per-material process-hazard
classifications are likewise caveat only. Unknown (no PubChem record) stays 0.5.
Reason (owner): these codes describe respirable powder handling, not film hazards; the
particulate hazard belongs in the caveat the PI reads, not in the rank.
Consequence on the recorded oxides: Al2O3, La2O3, and Y2O3 move to the allow score and tie
with HfO2 at 1.0; TiO2 (H351) and SiO2 (H350) stay at 0.5.
Alternative: any GHS code flags at 0.5 (the first pass).

### 2026-11-02 Photocatalyst window upper edge is 3.3 eV
Decision (owner): `oxide_photocatalyst.yaml` uses a hard window of 2.0 to 3.3 eV. The upper
edge was set after the first scoring pass so that the recorded compendium medians of TiO2
(3.30 eV) and BaTiO3 (3.06 eV) fall inside it. An application choice, recorded with its origin.
Alternative: 3.0 eV (the Track 0 discovery recording), under which no baseline oxide ranked.

### 2026-11-02 Recorded data versus the owner's directional expectations
Decision: tests assert what the recorded data gives and the differences are reported, not
tuned. Under the first photocatalyst profile (2 to 3 eV hard window, best available source) the
experimental medians of TiO2 (3.30 eV) and BaTiO3 (3.06 eV) fell above the window edge, so no
baseline oxide ranked; the owner moved the edge to 3.3 eV (decision above).
With the dielectric weight on (test band 10 to 30), HfO2 and ZrO2 already sit above SiO2's
would-rank at weight 0, so the test asserts the margin widens. Rocksalt BeO (mp-1794, ICSD
163825, 481 meV/atom) is excluded by the beryllium rule first and by hull once the hazard
rules are lifted; both appear in the decision log.

### 2026-11-03 Excluded rows keep their full breakdown
Decision (owner): the scorer computes every criterion for every candidate, excluded or not,
and the bundle carries the full `ScoreBreakdown` (values, sources, flags such as a band gap
conflict) on excluded rows with `total` None. Only the criterion that raised the exclusion is
marked missing with the reason "excluded by <rule>", because a hard exclusion has no
normalized value. The audit view can then show why ThO2 would have scored well and why it is
out. Alternative: stop at the first exclusion and leave the other criteria empty.

### 2026-11-03 Hazard weight floor of 0.1
Decision (owner): `site_profile.default.yaml` sets the hazard weight bounds to 0.1 to 1.0 as
an admin default, so a scientist cannot weight the hazard criterion out of a ranking; a request
below the floor is clamped and the clamp is shown (test query E1). Exclusions apply at any
weight. Alternative: a 0.0 floor, under which "set the toxicity weight to zero" silently
removed the only soft hazard signal.

### 2026-11-03 Non-oxide anion policy carries a calibration caveat
Decision (owner): when `simplicity.anion_policy` is not `strict_oxide` the scorer emits
`stability_cutoff_oxide_calibrated` on every row, with the text entered in the profile's
stability section (the 94 meV/atom cutoff is the Sun 2016 binary-oxide percentile) and the
renderer resolves it like every other caveat. The trigger is code and the text is config, so
the LLM cannot drop or reword it; this replaces the idea of a prompt fragment. The
nitride-specific statement in the owner's notes stays a TODO in the config entry until it is
sourced. Alternative: a fixed sentence in the rationale prompt, which the verifier could not
check.

## Track B: agent, verifier, renderers, CLI

### 2026-11-02 One bounded conversation per step, one tool offered
Decision: the agent runs four steps (parse, classify, rationale, relax), each a short
conversation that offers exactly one of the four tools; the model acts only by calling it. A
text-only reply is nudged once and then fails the step; refusal and context overflow fail
without retry; the budget (CoreConfig tool calls, tokens, seconds) is checked before every
request and a breach ends the step as partial with the reason. Every request appends a
decision-log entry; the entry for the rationale step records slot ids and lengths, never the
unverified text.
Reason: one tool per step makes the contract testable with a scripted fake and keeps the
model from mixing steps; a loop that offered all four tools would need the code to police
which one was legal when.
Alternative: one long conversation with all four tools and tool_choice forcing.

### 2026-11-02 Strict tools with automatic tool choice; the pinned model id has no date
Decision: every tool is declared `strict: true` with a closed schema (refs inlined, every
object closed, every property required, optionals nullable, weights as named fields) and
`tool_choice` is left automatic, because the pinned model rejects forced tool choice. The
model id is pinned in settings as the exact string the provider serves (`claude-opus-5-5`);
current ids carry no date suffix, and the id is recorded in every bundle's `model_version`.
Reason: strict schemas make the model's input validate exactly; the prompt names the tool
instead of forcing it.
Alternative: forced tool choice (rejected by the model); a dated alias (none exists).

### 2026-11-02 The model picks a relaxation; code computes it
Decision: when fewer than top_n candidates rank, code enumerates the admissible threshold
changes (band_gap_min_ev, band_gap_max_ev, max_elements): for each, the smallest change that
admits the next excluded candidate with the exact new value and how many already-fetched
candidates it admits. The model may only pick a choice id and phrase it without digits. The
CLI shows "lowering X to V adds N" and applies it only on an explicit yes, as a new query
(new config sha, new run) with the user's approval in the decision log.
Reason: invariant 3; a number the model proposed would be a number the model computed.
Alternative: the model proposes the value and code checks it.

### 2026-11-02 Prompt hashes per step; the run records the combination
Decision: prompts are a fixed-order concatenation of versioned fragments keyed by the
TEMPLATE_FRAGMENTS ids; only the rationale step reads the query settings. Each step has its
own sha256 over the system prompt, the provider-neutral tool spec, and the static user-turn
fragments; `RunMetadata.prompt_hash` is the sha256 of the four joined. The classifier cache
key uses the classify-step hash with the abstract sha256 and the model id, so a change to the
rationale prompt or a verbosity setting never invalidates classified abstracts.
Reason: the bundle has one prompt_hash field; one hash over all steps would make the cache
depend on prompts it never used.
Alternative: one hash over everything.

### 2026-11-02 Display precision is one table and number checks are string equality
Decision: `render/precision.py` holds the places per unit; renderers format through it and
the verifier accepts a written number only when it equals one of the renderings of a bundle
value (every precision from zero places up to the unit's, in the stored unit and in meV for
energies), computed in decimal with half-up rounding. Raw floats are never admitted. The
allowed set is scoped by slot id to that composition's numbers plus run-level counts.
Reason: `round()` in binary float is half-even and representation dependent; a renderer must
never emit a string the verifier rejects, and a round-trip test proves it.
Alternative: float comparison within a tolerance.

### 2026-11-02 What the verifier consumes before it scans digits
Decision: per slot, in order: template tokens (validated against the bundle index), record
ids by shape, GHS hazard codes (only those the bundle reports for the composition),
oxidation-state tokens such as Cr(VI) (element must occur in the composition), then
formula-shaped tokens parsed with pymatgen only when they carry a digit or parentheses or
match a bundle composition exactly. Each pass replaces what it accepts with a placeholder.
A failing fragment is the whole sentence, removed and logged; a slot emptied this way is
unverified and the renderer shows the template text. Evidence quotes are exact substrings of
the stored abstract with no Unicode normalization; fulltext-scope hits are never verified
and never rise above computed_only.
Reason: pymatgen parses "CVD", "ALD", and "H335" as formulas; the order keeps acronyms and
hazard codes out of the formula check and keeps a number hidden in a formula-like token
(Hf2O5) a formula failure.
Alternative: a single regex pass over digits.

### 2026-11-02 Caveat text: config for chemistry, code for run state, a marker otherwise
Decision: caveat ids resolve through `render/caveats.py`: hazard flags, process hazard
(template plus the per-material classification), unknown hazard, the stability cutoff
mismatch, band offsets, and the ECHA attribution come from config entries with status
`entered`; the data-state ids (experimental gap composition level and unreferenced,
reference value pending, anion undetermined, evidence unclassified, enrichment missing) use
code-owned text that states what the run did; any id without text renders
"caveat text not entered: <id>". The deposition-method enum the classifier uses is
code-owned from the owner's list; the site profile's pending list is not read, and Track A
enters the identical list there.
Reason: chemistry claims come only from sourced config; a run-state statement is not a
chemistry claim; an invented sentence is worse than a visible gap.
Alternative: all caveat text in config, including run-state text.

### 2026-11-02 Runs are files; cassettes are a fetch path; the scorer is a port
Decision (owner): completed bundles are JSON files under `<data_cache_dir>/runs/<run_id>.json`
read by replay, diff, and export. The CLI's `--fetch store` uses the Postgres-backed Runner
with FETCH_MODE from settings; `--fetch cassettes` serves the recorded interactions by cache
key through the same URI mapping the seed script uses, with no database. The pipeline scores
through a port: Track A's `scoring.scorer` when importable, else the sample stand-in that
copies the sample bundle's scoring by composition and says so in the run note. Replay re-runs
the stored criteria against stored data under a new run id with the source run logged.
Reason: the runs table has no bundle column and provenance is frozen; a no-database path is
what a cold run and CI need; the scorer interface lands after Track B started.
Alternative: a bundle column (frozen area); a cassette-only CLI.

### 2026-11-02 Diff attributes through evidence labels, policy hashes, and displacement
Decision: a composition's data fingerprint is every provenance reachable from its summary
minus fetch time and raw row id. Causes listed in fixed order, all that apply: candidate_set,
data, config (config sha or hazard policy hash; `RunMetadata.policy_version` is the short
sha256 of the policy file because its schema_version never changes on an edit), model (only
when the composition's evidence labels changed; otherwise noted as not causal), and displaced
by a named changed composition. "unattributed" means scorer code changed; the code version
is in the decision log's start entry.
Reason: the model touches rank only through labels; a policy edit was invisible to the
config sha; a rank shift caused by a neighbour has no cause of its own.
Alternative: one cause per change by priority.

### 2026-11-02 The OpenAI-compatible provider is tested against a fake only
Decision: the provider switch covers anthropic and bedrock through the SDK and
openai_compatible through httpx against a base URL from settings. The last is exercised only
with a fake transport in tests; no real server was recorded.
Reason: no OpenAI-compatible server is available to record; the mapping is small and typed.
Alternative: omit the provider until a server exists.

### 2026-11-03 Budgets are per step; at most five abstracts per candidate
Decision (owner): `CoreConfig.step_budgets` holds one `StepBudget` (model requests, tokens,
seconds) for each of parse, classify, rationale, and relax, replacing the single global pool
(`max_tool_calls`, `max_tokens`, `max_seconds`); `CoreConfig.max_abstracts_per_candidate` is
5, taken in the literature search's result order. The run records `<step>.<counter>` under
`budgets_used` and `budgets_limit`, including the CLI's parse step. Editing the budget fields
in `config/schema.py` was owner-authorized on 2026-11-03.
Reason: one pool let a long classify phase starve the rationale step; per-step limits make
a partial run name the step that ran out.
Alternative: one pool with reservations per step.

### 2026-11-03 The quote check is skipped for not_relevant and no_abstract
Decision (owner): evidence hits labeled `not_relevant` or `no_abstract` make no claim about
the material, so the verifier records them unverified without a quote check; the four
evidence tiers (computed_only, bulk_synthesized, thin_film_deposited,
dielectric_characterized) always need a verbatim sentence, and a missing one is a
`quote_mismatch` failure.
Reason: a sentence cannot support "not about this material"; demanding one produced
spurious failures.
Alternative: require a sentence for every label.

### 2026-11-03 Discovery needs a gap floor; enrichment repeats until the top K is enriched
Decision: every oxide with up to three elements is above the discovery ceiling, so a
discovery query takes its gap floor from the query, else the profile's hard minimum, else
its soft preference start (5.0 eV for the dielectric profile), and its gap ceiling from the
query, else the profile's hard maximum. `scoring_profile_from_yaml` now fills
`hard_min_ev` and `hard_max_ev`, which the schema declared but the loader skipped (a second
owner-authorized edit of the frozen loader; the photocatalyst window never reached the
filter before). After the summary-level scoring pass the pipeline enriches the top K plus
the anchors, classifies their hits, and scores again; because an exclusion found by
enrichment admits the next candidate, it repeats until the final top K is enriched, bounded
by twelve rounds and five times top_n compositions. The two queries the CLI runs offline,
oxides at or above 5.0 eV (895 documents) and the 2.0 to 3.3 eV window (3835), are
recorded with the adapters of every composition that reached a top 10 along the way
(`fixtures/compositions.yaml`, `discovery_top10_*`).
Reason: the owner asked for discovery to run offline end to end; a single enrichment pass
left unenriched rows in the shown top 10 as soon as enrichment excluded one.
Alternative: enrich a fixed margin (top 2K) once.

## Track E: eval and validation

### 2026-11-02 Spearman by hand, cross-checked against scipy
Decision: `validation/spearman.py` computes rho from average ranks (ties share the mean of
their positions); a test compares it with `scipy.stats.spearmanr` on fixed and random inputs.
Fewer than two pairs or a constant rank vector returns None with the reason, never a number.
Reason: the eval adds no dependency (pyproject is frozen; scipy is only transitive through
pymatgen), and tie handling is visible in twenty lines the reviewer can read.
Alternative: call scipy directly.

### 2026-11-02 Yim polymorph rows collapse to the best figure of merit per composition
Decision (owner): Yim 2015 lists one row per ICSD entry; the scorer ranks composition groups.
For each table, one entry per composition ordered by its highest f_fom in that table; ties
get average ranks. c-BeO is the BeO group; the phase prefix stays as data. The Spearman is
taken over the compositions the scorer ranked; every excluded composition is listed with its
rule, and the compositions whose recorded literature search returned no abstract (ten with no
match at all, two more with matches but no abstract) stay in the correlation and are listed
separately under evidence tier "no abstract", never "no support".
Reason: the paper's polymorph-level numbers cannot be matched to MP ids without a second
sourcing pass, which the scope rule closes; the best polymorph is the paper's own reason for
listing the composition.
Alternative: match rows to the ground-state polymorph by ICSD id and report unmatched rows.

### 2026-11-02 Yim fixture erratum: Tables 2 and 3 band gap column
Decision (owner): every row from Tables 2 and 3 carried the space group in `band_gap_ev`
(61 rows). The values are nulled with a `data_errata` block; a test fails if any gap equals
its space group or if a Table 1 gap is missing. The owner re-enters the column after the
deadline. The metric reads `f_fom` only, so no result depends on the column.
Reason: a wrong value shown as data is worse than a null with a note.

### 2026-11-02 Known-dielectric recall list is a validation fixture citing the owner
Decision (owner): `fixtures/validation/known_dielectrics.yaml` holds HfO2, ZrO2, Al2O3, Y2O3,
Ta2O5 and K=5, sourced to the owner's Track E prompt; Y2O3 and Ta2O5 are re-sourced to
Robertson (2004) when the PDF is on disk. The scorer never reads this file.
Reason: `config/reference_values.yaml` has entries for Al2O3 only among the five; a recall
expectation is not a scoring input and does not need the config's sourcing bar.

### 2026-11-02 Band gap calibration and the conflict tolerance
Decision: `validation/calibration.py` pairs each recorded oxide's experimental median with the
TBmBJ and PBE gaps of its scored polymorph, reports MAE with n and every pair, and derives the
conflict tolerance as twice the TBmBJ MAE with a sha over the pairs and snapshot hashes. ThO2's
two conflicting compendium rows stay in the pair as recorded; the owner's note about them is
beside the value in `config/reference_values.yaml`. The number is written to the scoring
profile in one separate, labeled commit after the rebase on Track A, since `config/` is Track
A's directory.
Reason: the profile itself defines the tolerance this way; the derivation and data hash make
the number reproducible.
Alternative: a hand-chosen tolerance.

### 2026-11-02 A temporary stand-in scorer ran the validation path before Track A merged
Decision: until Track A merged, `validation/stand_in.py` reproduced the sample bundle's
illustrative normalizations with Track A's vocabularies so the groups-to-report path ran end
to end. Its run note said it was not scoring and no results from it were committed. It was
deleted on 2026-11-02 at the rebase onto main after Track A's merge; `validation.track_a`
is the only scorer the validation run uses.
Reason: the metrics are tested on synthetic bundles, but only a full run proves the loaders,
the metrics, and the report agree on 61 compositions.

### 2026-11-02 The judge decides two items and nothing else
Decision: the LLM judge grades caveat presence and PI-view summary level only, from a rubric
file, with a per-item reason; structure (ranks, exclusions, flags, refusals, config unchanged,
verifier failures, missing markers) is decided by named checks in `evals/checks.py`. The fake
judge is the CI default; the Anthropic judge (`evals/judge.yaml`, `claude-opus-5-5`, effort
low, structured output) records a declined request as the verdict `judge_declined` rather than
retrying on another model. A sample of verdicts goes to `evals/judge_sample.md` for the owner
to grade; the report shows the agreement rate once graded.
Reason: a judge is the one place a model's opinion enters the eval; keeping it to two
questions with a graded sample keeps it auditable.
Alternative: a rubric-wide LLM grade per case.

### 2026-11-02 Adversarial cases report task completion and attack success from named checks
Decision: an F case carries `task_completion` checks (all must pass) and `defenses` checks;
the attack succeeded if any defense failed. Each case names one OWASP LLM Top 10 (2025)
category from a closed table. A1 and F1 lead every listing.
Reason: "attack success" has to be a definition the reader can open, not a judgment.

### 2026-11-02 Pre-registration of the scoring config
Decision: `uv run python -m evals prereg` records the effective config sha, the config file
hashes, the fixture and cassette hashes, and the commit before validation runs; the report
shows the pre-registered and current shas side by side when they differ and names the files
that changed.
Reason: a tuned config after the fact must be visible as such.

### 2026-11-02 A second Yim correlation under a Yim-like configuration
Decision: the Yim comparison runs twice and both rhos sit side by side in docs/EVAL.md. The
default column is the profile as entered. The Yim-like column (owner decision 2026-11-02) sets
query-level weight overrides within site bounds: stability, band gap and dielectric constant at
1; hazard, simplicity, evidence, deposition method and cost at 0. The profile file is not
changed, so the default run's config sha is unaffected and the Yim-like run gets its own sha.
Exclusion rules (hazard, stability cutoff, anion policy) still apply at weight 0. The
dielectric target band is read from the profile file as written; Track A's strict loader drops
it while its status is not `entered`, so the results carry the band and its status beside the
rho, and the run note says it was used for the validation comparison only.
Reason: the default profile weights evidence and hazard, which Yim's figure of merit does not;
a rho under weights closer to Yim's inputs says whether a weak default rho comes from those
criteria or from the scorer's stability and gap handling. Alternative considered: a second
profile file under config/scoring_profiles (rejected: config is Track A's, and a profile that
weights a `pending_verification` criterion would fail the strict loader by design).

### 2026-11-02 The band gap conflict tolerance is written to the profile from the calibration
Decision: `config/scoring_profiles/oxide_dielectric_thin_film.yaml` gets
`conflict_tolerance_ev: 1.345` with status `entered`, the derivation (2 x the TBmBJ MAE of
0.672 eV over the six recorded baseline oxides that have both a TBmBJ and an experimental
value), the data hash from `validation/results/band_gap_calibration.json`, and the entry
attribution. This is the one Track E change outside its own directories, in its own labeled
commit, approved by the owner on 2026-11-02. The pre-registration was taken before the write,
so docs/EVAL.md shows the pre-registered and the current config sha side by side and names
this file as the one that changed. The validation results are re-run under the new sha so the
committed results match the committed config.
Reason: the owner's prompt sets the rule (twice the measured TBmBJ error) and asks for the
value, its derivation and the data hash in config. ThO2's pair (error 1.613 eV) is kept as
recorded; dropping it would be a hand choice.
Alternative: leave the value in the results JSON for Integration to copy (rejected by the
owner: the commit goes to the profile, separate and labeled).

### 2026-11-02 The eval cases run through Track B's pipeline with a scripted model in CI
Decision: `evals.execute.PipelineExecutor` runs each case through `agent.pipeline.run` with
Track B's own parse step, Track A's scorer behind Track B's port, the verifier and the
renderers. Data comes from recorded cassettes (`--fetch cassettes`, the CI default) or from
the seeded store with `FETCH_MODE=replay` (`--fetch store`); either way nothing touches the
network. The model is `evals.pipeline_llm.CaseScriptedLLM` with `--llm fake`: it implements
Track B's client protocol and answers from the offered tool and the case file (refusal
category from the harness triggers, otherwise the case's mode and candidate list; keyword
labels with a verbatim supporting sentence; token-only rationale). `--llm live` uses the
configured provider; `--llm none` skips the model and takes criteria from the case file. No
classifier cache, so repeats classify anew. Every bundle is saved under
`.data-cache/evals/runs/<run id>.json`. An F case with `injected_fixture` has that OpenAlex
response served for `injected_into`'s literature search in place of the recording.
Reason: the structural checks must see what the pipeline produces, not a copy of a bundle;
CI cannot call a model, and a scripted client that goes through the real loop exercises the
parse, classify, rationale and verify paths. A keyword label is an arbitrary label, so the
results name the executor as `pipeline:fake:cassettes` and evidence-dependent ranks from CI
are read with that in mind; live runs are the results.
Alternative considered: Track B's queue-replaying `FakeLLM` (rejected: the number of
classify calls depends on the data, so a fixed queue is exhausted or wasted).

### 2026-11-02 Two Track B behaviors the executor surfaced, left as findings
Finding 1: with the baseline eleven as a candidate list, classifying the top ten candidates'
hits spends the core budget of 40 tool calls before the rationale step, so the run is partial
with "rationale not written: max_tool_calls (40) reached" and the rationale is template text.
The A1 check `run_completed` reports this; the budget lives in the frozen `config/schema.py`
and is the owner's to raise.
Finding 2: the classifier accepts a `not_relevant` label without a supporting sentence, but
the verifier checks a quote on every label except `no_abstract` and `unclassified`, so such a
hit is dropped as a quote mismatch. The scripted model quotes a sentence on every label so the
verifier passes; whether the verifier or the classifier should change is the owner's call.
Unverified whether either behavior is intended.

### 2026-11-03 A data-level Yim correlation, paired by structure, beside the two scorer columns
Decision: `validation/data_level.py` computes, per Yim table, Spearman rho between Yim's
figure of merit and (PBE gap x e_total) read from our records, with no scoring policy: no
weights, normalization or exclusions. Pairing is by structure, row by row: the Yim row's
ICSD id against the ICSD ids the Materials Project records carry in `database_IDs`; when none
matches, the MP polymorph of the same reduced composition and the row's space group number
(lowest hull first when several); otherwise the row is unpaired and listed with the reason.
The gap is the MP PBE gap on the paired polymorph, one source for every row; e_total is the
MP DFPT value on it. The experimental median from the expt_gap snapshot is a separate column
where the composition has one, with a second rho over those rows. Rows without both values
are listed and left out; nothing is filled. docs/EVAL.md shows the two data-level columns
beside the default and Yim-like ones, which are unchanged. Owner decision 2026-11-03,
replacing the first version (2026-11-02) that paired by composition with a best-available
gap.
Reason: Yim's rows are structures, and a composition-level pairing can set a row against a
different polymorph than the paper computed. One gap source keeps the column comparable
across rows; the experimental column shows where measurement and PBE disagree without
mixing them. The two scorer columns mix data and policy; a correlation from the records
alone says whether a weak scorer rho comes from the policy or from the data our sources hold.
Alternative considered: Yim's own gap and dielectric values from the paper (rejected: the
question is what our records say).

### 2026-11-03 Case files from the owner's catalogue, verbatim, with the nearest structural check
Decision: `evals/cases/<id>.yaml` holds one case per query in `internal/test-queries.md`
(43 cases, A1 to G5). Requests and expectations are copied verbatim; B1's request carries the
owner's wording "between 2 and 3.3 eV" (decision 2026-11-03, matching the photocatalyst
profile's window). Each case names structural checks; where the catalogue expects something
no query setting or check can express (a per-run anchor, a hull-cutoff setting, a glossary
term, a clamp whose site bound is already 0), the nearest check is still listed and its miss
is reported with the detail, not dropped. Four cases carry `skip_reason` and are reported as
not run: B2 (no nitride profile exists; the anion policy is profile-level), E3 and E4 (console
and YAML actions, not chat queries), G3 and G4 (two-run diff and a database version change).
Three case-file fields drive the scripted model and the executor: `profile` (the CLI's profile
choice), `fake_parse` (what the scripted model answers for parse_request where the live model
would use judgment: C1 asks for the missing fields, C6 resolves alumina and sapphire to Al2O3),
and `llm` (G5 runs with no model). A parse that asks for fields the case does not give is a
clarification outcome, not an error: no run starts and `clarification_requested` reads it.
Reason: the catalogue is the owner's pre-registered expectation list; the harness must show
where the system meets it and where it cannot, in the system's own terms.
Alternative considered: drop the expectations the harness cannot check (rejected: a missing
row hides a gap the owner wrote down on purpose).

### 2026-11-03 Repeats are compared on ranks, exclusions and prompt hash
Decision: `CaseResult.repeats_identical` is true when every repeat's candidate rows (rank and
exclusion rule) and prompt hash match; rationale wording is not compared, as G1's expectation
allows it to vary. G2 (replay) is a second run from the same confirmed criteria over the same
recorded data and reports the same comparison.
Reason: the owner's G1 expectation names exactly those three things.


## Track F: fixes from the eval run

### 2026-11-03 Principle: the discovery prefilter sends only hard rules, at their loosest admissible value
Decision (owner): the discovery query to Materials Project receives only hard rules, and
each at the loosest value any admissible setting could reach. The PBE gap floor is the
profile's `discovery_pbe_floor_ev`, the gap ceiling the profile's hard maximum, the hull
limit the site's maximum cutoff (`stability_cutoff_bounds.max`), the element count the query
or profile maximum. Soft preferences (the 5 eV gap start) and tighter query settings (a query
gap window, a lower hull cutoff) are scorer exclusions, so excluded rows stay in the fetched
set and relaxation proposals count from it. `agent/pipeline.py::discovery_filter` is the one
place this is applied.
Reason: the 5 eV soft preference sent as `band_gap_min` dropped HfO2 (max PBE gap 4.41 eV),
ZrO2 (3.96) and ThO2 (4.42) before scoring, so A1 could not rank them or show ThO2's
exclusion, and a query minimum sent to the API left relaxation nothing to count.
Alternative: send every setting to the API, which is cheaper per query and hides why a
material is missing.

### 2026-11-03 Discovery PBE floors per profile
Decision (owner): `oxide_dielectric_thin_film` sets `discovery_pbe_floor_ev: 3.0`: the 5 eV
soft preference times 0.6, for the PBE underestimate the Materials Project documentation
reports ("typically, we find that band gaps are underestimated by about 40%", Electronic
Structure methodology page, checked 2026-11-03). `oxide_photocatalyst` keeps its hard window
(floor 2.0, ceiling 3.3). The recorded queries match 3748 and 3082 documents, under the
10,000 ceiling.
Alternative: the experimental factor of 1.6 on the same page, giving 3.125 eV.

### 2026-11-03 Hull cutoff is a query setting inside site bounds
Decision (owner): `QuerySettings.e_above_hull_max_mev` (default the profile cutoff) is
clamped to `site_profile.default.yaml#stability_cutoff_bounds`, 0 to 94 meV/atom, and the
clamp is shown (F11 asks for 2000 and gets 94). The effective value is
`EffectiveConfig.stability_cutoff_mev`, part of the config sha, and the scorer reads it
instead of the profile value. At a cutoff of 0 there is no ramp: rows on the hull score 1.0
and every other row is excluded by `stability.cutoff`.
Alternative: a floor of 24 meV/atom (the DFT accuracy), under which A5's "on the hull only"
would be clamped.

### 2026-11-03 Per-run anchors stay ranked
Decision (owner): `QuerySettings.extra_anchors` adds anchor rows for this run (A3: "compare to
what we use now, HfO2"). A per-run anchor that is also a candidate keeps its rank; its anchor
row's would-rank equals that rank. Profile anchors (SiO2) still never take a slot. Anchors the
discovery query did not return are fetched by name, so every anchor row carries the same
cross-checks.
Alternative: remove the composition from the ranking like a profile anchor.

### 2026-11-03 One config loader for every path
Decision: `config.schema.scoring_profile_from_yaml` and `site_profile_from_yaml` delegate to
the strict loaders in `scoring/profile.py`. Before, the CLI, API and eval path read neither
weight bounds nor site defaults, so the hazard floor never clamped there (E1).
Alternative: keep two loaders and copy each new field into both.

### 2026-11-03 Run-shaped recording with a two-round cap
Decision (owner): `scripts/record_case_gaps.py CASE...` runs an eval case through the real
pipeline, serves recorded cassettes first, fetches only misses live, and writes them to
`fixtures/adapters/<source>/run_<case>.yaml`; it then replays the case with no network. At most
two live rounds per case; anything still unavailable is listed in the report, not recorded
further. The recording manifest's `_case_recordings` lists what remained per case.
Reason: the per-composition recorder could not know which compositions a discovery run
enriches; recording the run records exactly the calls it makes.
Alternative: widen `fixtures/compositions.yaml` by hand after each replay.

### 2026-11-03 Yim-like validation runs at the hazard floor
Decision: the Yim-like validation configuration sets hazard to 0.1, the site floor, since 0 is
no longer admissible. Its label says so.
Alternative: let validation bypass site bounds, which no other run can.

### 2026-11-03 Site glossary entered
Decision (owner): the site glossary maps energy above hull to stability margin, band gap to
insulating gap, polymorph to crystal form, and hull to stability reference, applied only when
terminology is general. The longest term wins, and a term also matches with its first letter
capitalized. Both views print the effective energy above hull cutoff, so D3's general view
names the stability margin.
Alternative: a glossary keyed by criterion id, which would miss the term in caveat text.

### 2026-11-03 Relaxation proposals are counted by re-scoring the fetched set
Decision (owner): when fewer than top_n rows rank, the pipeline lists relaxations of the query's
gap window, element count, and hull cutoff (inside the site bounds). It re-scores the
already-fetched groups under each relaxed value, and every proposal states "adds N", the number
of newly ranked candidates. A value that admits nothing new is dropped. At most three choices
and eight re-scores are made per setting. When no proposal adds a candidate, the decision log
says "no relaxation is admissible within site bounds" with the reason. Nothing is applied. The
CLI offers the logged proposals and the eval harness reads them from the log.
Alternative: count excluded rows by their raw value (the first pass), which counted rows that
another rule still excludes.

### 2026-11-03 Discovery ceiling override for evals only
Decision (owner): `Case.overrides.discovery_ceiling` lowers the refuse-to-truncate ceiling for
one eval case (C3 sets 500 against the 3748-document dielectric query), through
`RunInputs.discovery_ceiling`. No query setting reaches it.
Alternative: record a query that matches more than 10,000 documents, a large fixture that
shows nothing new.

### 2026-11-03 Unresolved candidate names are reported, the run proceeds
Decision (owner): a candidate name that is not a chemical formula is listed in
`ConfirmedCriteria.unresolved_candidates`, logged "not found in any source", and shown in both
views. The other names are ranked. The parse fails only when no name resolves. Typed answers
at the CLI confirmation stay strict. The new bundle fields are defaulted, so
`BUNDLE_VERSION` stays 2 and older bundles still validate.
Alternative: fail the parse on any bad name (the first pass, C5).

### 2026-11-03 Requested properties without a source are carried as unavailable
Decision (owner): the parse lists the properties a request names (`requested_properties`). Code
maps them through `config.schema.PROPERTY_CRITERIA`, a closed table of names. Anything unmapped
goes to `ConfirmedCriteria.unavailable_properties`, is logged "unavailable from configured
sources", and both views state it. No row or value changes. The parse prompt gains one sentence,
so the prompt hash changes.
Alternative: let the model decide availability, which would put a source claim in model text.

### 2026-11-03 B1 expectation
Decision (owner): B1 expects TiO2 ranked, not excluded, with its H351 flag, inside the top 5%
of ranked candidates, and Al2O3 only in the exclusion list by `band_gap.hard_max`. The profile is
unchanged. `ranked_near_top` gains `within_fraction`, and the new check `only_in_exclusions`
covers Al2O3.
Alternative: a fixed rank such as 10, which the 3082-document photocatalyst set does not support.

### 2026-11-03 Nitride profile
Decision (owner): `config/scoring_profiles/nitride_wide_gap.yaml` uses the dielectric
machinery with these changes:
- `anion_policy: strict_nitride`
- `hard_min_ev: 4.0`
- no soft preference
- `discovery_pbe_floor_ev: 2.4` (4.0 x 0.6, the same 40% rule)
- conflict tolerance open, because the 1.345 eV tolerance was derived on oxides
- no dielectric target band
- no anchor

The 94 meV/atom cutoff applies with the oxide-calibration caveat on every row. B2 runs under it.
Alternative: switch the anion policy per query, which the profile contract does not allow.

### 2026-11-03 G3 is a two-run case; the run diff separates data from enrichment
Decision (owner): `Case.compare` reruns the case under changed settings (G3: stability weight
0.5) and `cli/rundiff.diff` joins the two bundles. When the config changed, data is a cause
only if a source version moved: the run's source versions differ, or a record in both runs
carries another version. Within one version a record's provenance differs only by the call
that supplied it. An enriched row carries the per-formula summary and thermo documents, and a
summary-level row the discovery page. Enrichment follows rank, so that difference follows from
the config change. With the config unchanged, any provenance difference is still data. G3 gives
1667 rank changes, all attributed to config.
Alternative: count any provenance difference as data, under which every config change that
moved the top K also looked like a data change.

## Track G: molecular solids, egress, fetch default, fixes, live eval

### 2026-11-04 Molecular solids are excluded by structural dimensionality
Decision (owner): every thin-film profile excludes a candidate whose scored polymorph has
structural dimensionality 0, with the rule `structure.molecular`.
- **Method:** `pymatgen.analysis.dimensionality.get_dimensionality_larsen`, on the bonded
  structure from `CrystalNN().get_bonded_structure` with defaults.
- **Bonding choice:** pymatgen's docstring gives CrystalNN as the bonding route for this
  function.
- **Input:** the scored polymorph's MP structure, fetched as enrichment (the top K and the
  anchors). It is recorded as `structure_<formula>` cassettes for the 88 compositions and in
  the run-shaped case cassettes.
- **Display:** every row records the value with its MP record, or why it is missing. Missing
  never excludes.
- **Rule order:** after the hazard rules and before the stability cutoff.

Reason: CO2 and H2O ranked inside A1's top 10 on PBE gaps and "thin film" literature hits.
Nothing in the scorer could tell a molecular crystal from an extended solid.

Citation: entered as pymatgen cites the function: Larsen, Pandey, Strange, Jacobsen, Phys. Rev.
Materials 3, 034003 (2019). The owner's instruction named npj Comput Mater 5, 26 (2019). The
mismatch is a TODO for the owner in the config entry; neither publisher page was readable here.

Alternative: a name list of known molecular oxides, which a discovery query would outgrow.

### 2026-11-04 Egress is enforced in code
Decision (owner): `adapters/egress.py` builds the allowlist from `CoreConfig.allowed_hosts`
plus the configured LLM endpoint.
- `HttpxTransport.get` checks every call before sending.
- The LLM SDK clients get an HTTP client whose request hook allows only the provider's own
  endpoint, read from the built client:
  - Anthropic: `api.anthropic.com`
  - Bedrock Mantle: `bedrock-mantle.<region>.api.aws`
  - OpenAI-compatible: the `LLM_BASE_URL` host
- A refused host raises `EgressRefusedError` and nothing is sent.

Alternative: a network-level allowlist in Compose. It is not built, and it would not cover a
CLI run on a laptop.

### 2026-11-04 The CLI fetch default follows Postgres
Decision (owner): `query` and `rank` default to `--fetch auto`. That is the Postgres store when
a 2-second connect to `DATABASE_URL` succeeds, otherwise the recorded cassettes. The choice is
printed to stderr and written to the decision log (step `fetch_source`).
Alternative: keep `store`, which failed outright on a machine without Postgres.

### 2026-11-04 Track G fixes
- The PI view renders the verified `summary:overview` slot as an Overview section.
- The verifier removes `hit_dropped` hits (unknown record id, quote mismatch) from
  `bundle.evidence`. The `VerifierFailure` records keep what was dropped.
- The CLI passes the parse budget into the run's `prior_budgets`. The relax budget is added to
  the saved bundle's `budgets_used` when the relax step runs, and to the next run's budgets
  when a relaxation is accepted.
- `exclude_non_commercial` is removed from the site profile and `SiteProfile`. The BY-NC
  exclusion stays unconditional in `mp.assemble` and `polymorph_exclusion`. A site switch
  would let a site turn the license rule off, and no use case needs that.
- The FAILURE_MATRIX row for the discovery floor names the renamed test.
- `fixtures/compositions.yaml` no longer calls `oxides_gap_5_plus` the dielectric default.
- `.env.example` lists `FETCH_MODE` and `EVAL_LLM`.
- CLAUDE.md (owner-authorized edit of a frozen file) drops Keycloak, `tsc`, and `oqmd`, and no
  longer calls the CLI commands stubs.

### 2026-11-04 Runs stay JSON files
Decision (owner): run bundles stay JSON files under `DATA_CACHE_DIR/runs`, not rows in
`triage.runs`.
- A bundle is a self-contained, versioned, diffable artifact.
- `replay`, `diff`, and `export` work without a database.
- The Postgres store keeps what every number cites: raw responses and fetch events.
- `triage.runs` stays reserved for the API, which will need queries across runs.

Alternative: write each run to `triage.runs` now, adding a database dependency to the offline
path for no current reader.

### 2026-11-04 The parse tool schema fits the API's union limit
Decision: `ParsedRequest.weights` is a list of `{criterion, weight}` items naming only stated
weights, replacing one nullable field per criterion.
Reason: the first live run returned HTTP 400 for every case. The Messages API rejects a strict
tool schema with more than 16 union-typed parameters, and `parse_request` had 21. It now has 13,
and `tests/agent/test_tools.py` counts the unions in every tool schema so CI catches a
regression without a live call. Track B's provider tests ran against fakes only, which is why
this surfaced on the first live run.
Alternative: drop `strict` from the tool, which would let the model send fields outside the
schema.

### 2026-11-04 Live-eval cost controls
Decision (owner): no Opus calls in evals. Live runs use `LLM_MODEL=claude-sonnet-5-5` for the
run only, and the judge config names Sonnet. Before any call, `python -m evals run --llm live`
prints each case's expected and worst-case API calls and refuses when the expected total
exceeds `EVAL_MAX_LIVE_CALLS` (30).
- A case starts only while calls used plus its worst case fit under that limit.
- Each live case's classify step is capped at `EVAL_MAX_CLASSIFY_CALLS` (20). A case over the
  cap is partial, never extended.
- Live runs read and fill the product's classifier cache.
- `scripts/cache_from_bundles.py` wrote the paid Opus classifications into that cache.
- `python -m evals score-saved` grades a saved live bundle with no call.

Reason: an unestimated live run of the discovery cases made about 230 Opus calls (about 3
dollars), and retries paid for A1 twice because the harness bypassed the cache.
Alternative: a spend limit on the API key alone, which stops a run without saying what it cost
per case.

### 2026-11-04 Live results kept beside the scripted ones
Decision (owner): the committed live results are:
- **A1** (claude-opus-5-5, graded from its saved bundle with no further call). 7 of 8 checks
  pass. The run is partial because Opus reached the 300 s classify and 120 s rationale time
  budgets. ZrO2 ranks 6 with 4 thin_film_deposited and 1 dielectric_characterized labels.
- **F1** (claude-sonnet-5-5): refused, passed.
- **C1** (claude-sonnet-5-5): missed. The model ran a discovery query for "Find me some good
  materials" instead of asking. Found live, then fixed in code (next entry).
- **F4** (claude-sonnet-5-5): approved but not run. The first request returned HTTP 400
  "credit balance is too low", so no call completed, and it was not retried.

The gzipped bundles sit in `evals/results/live/bundles/`, and EVAL.md lists the live results in
their own section.
Alternative: rerun everything live, which the owner declined on cost.

### 2026-11-04 Clarification is decided in code
Decision (owner): the parse lists the chemistry a request names (`requested_chemistry`). Code
asks for application, chemistry, and property preference before any fetch when a discovery
request names no candidates, no chemistry, no requested property, and no property setting,
whatever the model chose. `pipeline.run` refuses such an outcome. A request that states only
output settings (view, verbosity, terminology, units, top_n) is treated as a follow-up and is
not stopped.

Follow-up cases D4, G3, and F9 ("Export this", "rerun A1", "Also write...") carry A1's request
as `context`, the earlier turn the parse sees. The harness has no conversation, and without the
context these cases would correctly be clarified.

Reason: live C1 showed that the parse prompt alone does not stop a vague request (CLAUDE.md:
if a prompt moves a failure, move the logic into code).
Alternative: a stronger prompt sentence, which the live miss shows is not a guarantee.

## Track C: API and web

### 2026-11-04 The API runs the pipeline; the browser never computes
Decision: the HTTP API (`api/app.py`) runs `pipeline.run` with the same pieces the CLI uses,
on a thread pool, and streams every decision-log entry as a server-sent event tagged code or
llm. The view routes serve the render package's view model as JSON, with every value already
formatted, so the browser only lays text out. The PI view JSON carries the PI columns and no
record ids; ids live in the audit view and the drill-down. Runs stay JSON files (Track G).
Alternative: let the web app compute totals or format numbers from the bundle, which would
put a number in a place the verifier cannot see.

### 2026-11-04 Development and tests use no model
Decision (owner): with `LLM_PROVIDER=none` the request box says parsing needs a configured
model and the confirm form is filled by hand, or the scientist uses Rank my list. Data,
scoring, verification and both views are real. API and browser tests use the fake model and
the recorded cassettes; nothing in Track C calls the Anthropic API. The demo configuration is
`LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-sonnet-5-5`, `CLASSIFY_MODE=cache_only`: one parse
call per Describe request and none for Rank my list.
Alternative: a scripted keyword parser in the UI, which would show a parse that no model made.

### 2026-11-04 Roles come only from the bearer token
Decision: three auth modes (`AUTH_MODE`): none (local, the role is `DEV_ROLE`), static tokens
(`STATIC_TOKENS=token:role,...`, refused when `SITE_MODE=true` unless `ALLOW_STATIC_TOKENS=true`),
and OIDC (RS256 JWTs validated against the issuer's JWKS, roles from `OIDC_ROLES_CLAIM`,
Keycloak realm roles by default). A role claimed in a body, a query string, another header,
or the request text changes nothing, and `tests/api/test_auth.py` sends each of those. Every
refusal is written to the audit log. `docs/PERMISSIONS.md` lists every route and screen action
by role, and `tests/api/test_permissions.py` checks it against the app. Weight bounds are
readable by every role, because the workspace sliders show the scientist their limits; the
console's other tables are FDE and admin only. OIDC validation allows 60 s of clock leeway:
the Keycloak container's clock ran ahead of the host's by a few seconds, which made every
token "issued in the future".
Alternative: Keycloak as the only mode, which the plan cut; the OIDC mode is what Keycloak
plugs into.

### 2026-11-04 Profiles are saved as new files; refresh is a flag for the next run
Decision: a scoring profile uploaded in the console is validated with the scorer's own
loader and the site bounds, and saved as `config/scoring_profiles/<profile>_v<version>.yaml`;
an existing file is never overwritten, so an old run's profile stays what it was. An admin
refresh marks a source for refetch on the next store-backed run (the Runner's refresh mode
for that source only), writes an audit entry with the required note, and leaves earlier
bundles untouched.
Alternative: edit the profile in place, which would change what an old run's name refers to.

### 2026-11-04 Wireframes followed, with these differences
The wireframes under `internal/wireframes/` (workspace confirm, run in progress, PI summary,
audit view, drill-down, workspace states, dark theme, console) set the layout and states. Shown
as the system really is, not as the wireframe sample text says:
- Sources are Materials Project, JARVIS, the experimental gap compendium, OpenAlex and
  PubChem; the wireframe's AFLOW and OQMD are not sources.
- A missing dielectric constant is shown as missing and never scored as zero.
- The hull cutoff clamps to 0 to 94 meV/atom, not the wireframe's 0.1 minimum.
- Sensitivity is shown per row in the audit view; the sensitivity and compare-runs pages are
  not built (the CLI `diff` covers comparison), and the tablet layout is not tested.
- The parsed request is not shown as highlighted phrases: the parse tool returns fields, not
  spans, and a highlight the model did not make would be invented.

### 2026-11-04 Open: the hazard flag caveat has no entered text
Finding: a row flagged through the GHS flag set (SiO2, H350) carries `hazard_flag` with no
config text, so both views show "caveat text not entered". The hazard policy's `ghs_flag_codes`
entry needs an owner-entered caveat sentence. Not written here (chemistry text is the owner's).

## Track D: deploy and docs

### 2026-11-04 One image serves the API and the web app; the split front is optional
Decision: the `api` Docker target carries the Python service, the built web app, the config,
and the recorded fixtures, so one container answers from recorded data with no keys and no
database. A `web-nginx` target and the Compose profile `split-web` serve the static app
separately and proxy `/api`, for sites that deploy the front end on its own.
Alternative: two mandatory images, which doubles what a cold run has to get right.

### 2026-11-04 Compose networks: internal and egress
Decision: Postgres and Keycloak sit on an internal network with no outside route; only the
API is also on the egress network. This limits which service can reach the internet. It does
not filter by hostname: the host allowlist is enforced by the application's egress check
(`adapters/egress.py`), and a network-level domain allowlist needs an egress proxy or a
firewall with domain rules, which the repository does not include. ADMIN_GUIDE and
ARCHITECTURE say exactly this.
Alternative: claim the network enforces the host list, which it cannot.

### 2026-11-04 Terraform is a validated reference, never applied here
Decision (owner): `infra/terraform` creates a VPC, private subnets with a NAT gateway, RDS
Postgres, an ECS Fargate service for the api image, Secrets Manager entries, and an optional
load balancer off by default. Providers are pinned; CI runs `fmt -check` and `validate`.
Security groups filter by IP and port, not hostname; the README says the hostname allowlist
is the application's and that domain filtering needs an egress proxy or AWS Network Firewall.
Alternative: no Terraform, which the plan allowed as a cut; the validated module costs little
and shows the shape.

### 2026-11-04 Apptainer recipe written, not built here
Decision: `apptainer/materials-triage.def` bootstraps from the `api` Docker image. There is
no Apptainer on the development machine, so the recipe is written against the definition-file
reference and the guide says the first build on a cluster is the test.
Alternative: omit it; the plan names it as a deliverable.

### 2026-11-04 Docs are checked against the code
Decision: `tests/test_docs.py` checks that every CLI command, script, and repository path the
README and the guides name exists, and that the README stays under 150 lines (owner rule).
The records (DECISIONS, FAILURE_MATRIX, EVAL, wire-findings) describe what was true when
written and are not checked. `docs/DESIGN_NOTE.md` is a placeholder link; the owner writes it
outside this repository and adds it later.
Alternative: trust the prose; the state report showed how fast it drifts.

### 2026-11-04 The cold run is a script with its output recorded
Decision: `scripts/cold_run.sh` clones, installs, builds, tests, serves from recorded data,
runs Rank my list over the API, and runs one eval case, printing PASS or FAIL per step with no
model call. `docs/COLD_RUN.md` carries the checklist and the last recorded output.
Alternative: a prose checklist alone, which nobody re-runs.

## Track H fixes: the human test session (Nov 4)

### 2026-11-04 Fresh-clone defaults: recorded data, Sonnet, model on, fallback to no model
Decision (owner): a bare `serve` works with no keys and no database. `FETCH_MODE` unset means
the recorded cassettes, even when Postgres answers; setting it selects the store. The model
defaults to `claude-sonnet-5-5`, never Opus, and `CLASSIFY_MODE` defaults to `live`. A
missing key, a rejected key, or an exhausted credit balance sets a process-level status
(`agent/llm_status.py`): the client is dropped, every step takes its no-model path, the app
shows a banner, and the run completes. One rejected request is the most a bad key costs.
`/criteria/resolve` returns the run's estimated model calls (one per abstract for the top
candidates, plus the rationale) with the step budgets as the hard cap. `scripts/cold_run.sh`
serves with the bare defaults. Tests cannot reach a provider: the SDK's request method raises
in every test.
Alternative: keep the store-first and Opus defaults and fail on a missing key, which is what
broke the README run in the test session.

### 2026-11-04 The API lives only under /api
Decision (owner): every API route is under `/api`, in `serve`, in the Vite dev server (the
proxy keeps the prefix), and behind the split nginx front. Every other path is the web app:
`/runs`, `/runs/<id>`, and the drill-down are client routes with the index.html fallback, so a
reload or a shared link shows the page. An unknown `/api` path stays a JSON 404.
Alternative: rename the client routes (for example `/results/<id>`) and keep the API at the
root; that leaves the next client route one name clash away from the same bug.

### 2026-11-04 Dev and site Compose files
Decision (owner): `compose.yaml` is for development: one network, Postgres and Keycloak
published on 127.0.0.1. `compose.site.yaml` applies the internal and egress split for site
deployments and removes the internal services' host ports. Docker publishes no host port for a
service whose only network is `internal: true`, which is why Track D's single file left
Keycloak and a freshly created Postgres unreachable from the host. The dev realm allows
`127.0.0.1:8799` for the browser sign-in test, which builds the app with
`VITE_AUTH_MODE=oidc` into a temporary folder (`WEB_DIST`).
Alternative: keep one file and attach the internal services to a second, routable network;
that publishes ports again and quietly undoes the isolation the split exists for.

### 2026-11-04 Experimental gaps never average across material forms
Decision (owner): each profile lists `criteria.band_gap.experimental_forms.preferred`. The
thin-film profile prefers `amorphous_film, thin_film, crystalline_bulk, compendium`; the
photocatalyst and nitride profiles prefer `crystalline_bulk, compendium, thin_film,
amorphous_film`. The first form with a point value is used and the median is taken within it;
values in other forms stay in the audit view and the drill-down with their form, marked not
used. `compendium` is the experimental gap table, whose form is not recorded, so it sorts last
for thin films. The criterion now records `used_record_ids`, the records that entered its
value; the drill-down's "used" column reads it. Al2O3 under the thin-film profile scores its
amorphous-film point (6.6 eV) instead of the 7.65 eV median of a film and a crystal. Rewriting
the pool also fixed the aggregate's provenance, which could name a range record that never
entered the median.
Alternative: a per-form median shown side by side with no rule for which one scores, which
leaves the choice to whoever reads the table.

### 2026-11-04 PBE-only gaps: the hard minimum excludes only below the PBE floor
Decision (owner), an extension of the Track F prefilter principle: when PBE is a candidate's
only gap source, the profile's hard minimum excludes it only below the profile's
`discovery_pbe_floor_ev`, the loosest PBE value the discovery query admits. Between the floor
and the minimum the candidate is kept and scored on the profile's shape, flagged
`pbe_only_below_window`, with the caveat "Only a computed PBE gap is available; PBE typically
underestimates gaps (Materials Project documentation)." from each profile's band gap block.
A scientist's own minimum applies to the value as written, so relaxation counts stay exact.
Under the nitride profile only the window 2.4 to 4.0 eV is affected; GaN's PBE gap of
1.738 eV is below the floor and stays excluded. The photocatalyst floor equals its minimum,
so nothing changes there.
Alternative: apply the window to the scientist's minimum too, which would make an explicit
9 eV minimum admit 3 eV PBE gaps.

### 2026-11-04 Template rationale carries caveat tokens, not caveat ids
Decision: the no-model rationale ends with a `{caveat:<composition>:<id>}` token for each of
the row's own caveats. The verifier checks only that the row carries that caveat; the
renderer fills the token with the caveat's config text, so chemistry text still comes only
from config and no id reaches the reader. Profile-wide caveats (`render/caveats.py`
PROFILE_WIDE: band offsets, the two stability cutoff notes, unclassified evidence, the ECHA
attribution) never enter a row's rationale.
Alternative: write the caveat text into the slot at run time, which puts config sentences
with digits and hazard codes through the verifier's number check and fails it.

### 2026-11-04 Equal scores display as tied
Decision (owner): ranked rows whose totals are equal at display precision show the first
rank of their group with "=" ("1="), and a note under the table says "Equal scores are tied;
tied rows are listed alphabetically." The bundle's integer ranks and the alphabetical
tie-break stay as they are, so prompts and replays are unchanged; `render/tokens.py`
`shown_ranks` computes the display once for the rank token, the views, and the CSV (`rank`
is the shown rank, `tied` says yes).
Alternative: a secondary sort key such as the band gap, which turns a tie into an order the
profile never asked for.

### 2026-11-04 The key caveat is the most row-specific one; profile-wide caveats show once
Decision (owner): a row's key caveat is the first present of the hazard flag, the band gap
conflict, the PBE-only window, near cutoff, and a theoretical ground state, then the row's
other caveats in enum order; a row with none reads "none specific to this row". Three flags
gain data-state caveats with the owner's text in `render/caveats.py`: band gap conflict, near
cutoff, theoretical ground state. Caveats every row carries by construction (band offsets,
the stability cutoff notes, unclassified evidence, the ECHA attribution) show once in an
"Applies to every row" panel above the table and leave the rows.
Alternative: keep the enum order, which put the standing band offsets sentence first on
every thin-film row and hid TiO2's hazard flag.

### 2026-11-04 Anchor placement names its place and neighbours
Decision (owner): a reference anchor reads "SiO2 (reference): would place 5th of 6, between
ZrO2 and TiO2". The count includes the anchor (`out_of` is the ranked candidates plus one),
and the anchor records the candidates just above and below its place (`ranked_above`,
`ranked_below`, defaulted fields). First and last places read "above X" and "below X".
Bundles written before this keep their stored count, which excluded the anchor; the sample
bundle's anchor fields were updated in place.
Alternative: keep "would rank N of M" with M the ranked count, which read as last place when
the anchor outscored the last candidate.

### 2026-11-04 Every Materials Project value links to its page
Decision (owner): every Materials Project record (summary, thermo, structure, dielectric)
carries `https://next-gen.materialsproject.org/materials/<mp-id>` as its URL, and
`records.record_url` derives the same link for MP ids in older bundles. The drill-down shows
a link for every value of the property, the stability one included, and the audit view
prints the link beside each MP record.
Alternative: link only the summary record, which is how the hull values lost theirs: the
thermo records overwrite the summary hull with provenance that had no URL.

### 2026-11-04 Typed candidates match names case-insensitively; unmatched entries are chips
Decision (owner): a typed entry is looked up first, case-insensitively, in the profile's
synonym table (formula keys and names, FDE-owned config), so "hafnia", "hfo2", and "HFO2"
are HfO2; otherwise it is parsed as a formula only when every symbol is a real element.
Pymatgen alone reads unknown capitals as placeholder species, so "SAPPHIRE" became a compound
and "HFO2" became HO2F. Unmatched entries are listed with a reason (red chips in the web app,
a sentence in the exports); an all-unmatched list is a missing `candidate_list` the form asks
for, never an error with a Python list, and starting a run with nothing to rank is a 422 in a
sentence. The model's parse tool still gets a tool error for an all-unmatched list so it can
ask. Eval case C5's rendered-text check follows the new wording.
Alternative: guess element capitalization ("co" as Co or CO), which invents chemistry.

### 2026-11-04 Offline misses say they are offline
Decision (owner): when a run reads recorded data (cassettes, or the store with no network),
a named composition with no recorded response reads "Not in the recorded data (offline
mode); available with live fetching". Only a live miss says the source has no summary. The
bundle records each miss with its reason (`criteria.not_fetched`), and the results page shows
it as a chip beside the unmatched names.
Alternative: one wording for both, which told the scientist Materials Project lacks CaO.

### 2026-11-04 Refresh notes are stripped and must have text
Decision (owner): the API strips the refresh note and refuses one that is empty after
stripping (422); the audit log stores the stripped note. The console's button already
required text; the API now enforces it for every client.
Alternative: rely on the console's check, which any other client skips.

### 2026-11-04 "What this screen cannot tell you" sits above the table
Decision (owner): the results page and the PI export show the "cannot tell you" list,
moisture sensitivity included, in one panel above the table beside the caveats that apply to
every row, so the limits are read before the ranks. A browser test checks the panel is above
the table and inside the first screen at 1280 by 900.
Alternative: keep it after the caveats, below a table that can run to ten rows.

### 2026-11-04 Strict anion policies require the simple anion's oxidation state
Decision (owner): `strict_oxide` requires every O at -2 and `strict_nitride` every N at -3 in
some pymatgen oxidation-state guess for the composition, with no other element negative in
that guess; if no guess gives the required state, the candidate is excluded by
`simplicity.anion_policy` with the reason "polyatomic or non-oxide/nitride anion (e.g.
peroxide, azide)". Peroxides and superoxides (BaO2, KO2) have no guess; azides (CaN6, SrN6)
guess N at -1/3. A composition with no guess at all is now excluded instead of flagged
`anion_undetermined`. Carbodiimides and dicyanamides (Li2CN2, KC2N3) pass, since pymatgen
assigns C +4 and N -3; whether they belong is the owner's call.
Alternative: the first guess's anion list only, which let azides into the nitride top 10.

### 2026-11-04 The composition-level gap note is profile-wide
Decision (owner): "The experimental band gap is reported for the composition, not for a
specific polymorph." shows once in the panel above the table and is never a row's key caveat
or part of its rationale.
Alternative: keep it per row, where it became the key caveat on most rows.

## Track H: usability

### 2026-11-04 Input limits are core configuration and one splitter lives in code
Decision (owner): `CoreConfig.max_request_chars` (2,000) and `max_candidates` (50) are
code-owned; `/api/parse`, `/api/criteria/resolve`, and `/api/runs` refuse over them with a
422 and a sentence, and the web app reads the limits from `/api/config/effective` for its
counter. Typed candidate text is split by `config/limits.py` (commas, semicolons, new lines;
blanks dropped; a case-insensitive repeat keeps its first spelling) when the confirm form
sends `candidate_text`; the CLI's `--formulas` uses the same function. The browser parses
nothing: matched entries come back from resolve as chips beside the red unmatched ones.
Red chips alone do not block Run (owner choice): unmatched names are reported as not found
and the rest are ranked, as the README demo and eval case C5 expect. Run is off while the
list is empty, over the limit, or the form is otherwise invalid. Adding the two fields moved
the config sha, so the golden scored bundle was regenerated.
Alternative: Pydantic `max_length` on the request fields, which answers with the list-shaped
validation detail rather than a sentence.

### 2026-11-04 The call estimate is shown before Run
Decision: the confirm form shows `estimated_model_calls` from `/api/criteria/resolve` as
"This run may make up to N model calls (hard cap M): basis", or the no-model note when the
total is 0. The sentence is composed from the server's integers and text.
Alternative: estimate in the browser from the candidate count, which would put a number on
the page that no code computed.

### 2026-11-04 A development role switcher, and no-auth refused in site mode
Decision (owner): with `AUTH_MODE=none` the header `X-Dev-Role` picks one of the three roles
for a request and the app's top bar shows a select; a value that is not a role falls back to
`DEV_ROLE`. The mode already gave every request a role with no identity, so the header adds
no reach, and two guards keep it local: `check_startup` refuses `AUTH_MODE=none` when
`SITE_MODE=true`, and the static and OIDC modes never read the header (tests send it in each
mode). `/api/me` reports `role_switch` so the select renders only where it works.
Alternative: a cookie or a query parameter, which the "nothing in a request changes a role"
tests would then have to carve out; a header that only one mode reads is the smaller hole.

### 2026-11-04 Help text lives in one file and is checked for coverage
Decision (owner): every plain-language explanation of a screen, criterion, flag, caveat,
exclusion rule, and evidence tier is in `web/src/help.ts`, each entry naming the document or
config entry its wording comes from and marked `review: "owner"`; no entry states chemistry
on its own authority. `GET /api/help/keys` lists the closed vocabularies and
`tests/test_help_text.py` fails when one lacks an entry. Tooltips are `abbr` elements with
the text as title and label, so the wrapped text is unchanged for the browser tests.
Alternative: text beside each component, which drifts and cannot be reviewed in one sitting.

### 2026-11-04 The guides are served from a two-file allowlist and rendered without HTML
Decision: `GET /api/help/{guide}` maps `scientist` and `admin` to the two guide files under
`docs/`; any other name is a 404 and no request value reaches the filesystem. The web app
renders the Markdown with react-markdown 9.0.1, which emits no raw HTML. The Docker image
copies the two files.
Alternative: bundle the guides into the web build, which shows the guide of the build, not of
the running API.

### 2026-11-04 The selection chart is hand-written SVG over a server view model
Decision (owner): the band gap versus dielectric constant chart draws from `ChartView` in
`render/views.py`: one point per scored candidate with both values, the gap being the scored
band gap raw value and k the scored polymorph's Materials Project DFPT `e_total` with its own
provenance. The dielectric criterion is not used because it is missing while its target band
is pending (owner decision). Tick labels and point texts are server strings; the PI view's
points carry no record ids. Rows without either value are listed under the chart. The SVG is
hand-written: no chart library, so nothing formats a number in the browser.
Alternative: a chart library, which brings its own number formatting and a dependency the
review would have to read.

### 2026-11-04 openai and gemini are experimental presets of the OpenAI-compatible client
Decision (owner): `LLM_PROVIDER=openai` and `gemini` reuse `OpenAICompatibleClient` with a
preset base URL (overridden by `LLM_BASE_URL`), their own key variable, and an explicit
`LLM_MODEL` (the Claude default is refused). The preset host joins the egress allowlist;
HTTP 401 and 403 set `invalid_key`, 402 and a quota 429 set `no_credit`. The console shows
the provider and model read-only. Both presets are marked experimental: not evaluated, and
their base URLs come from the providers' public documentation, unverified on the wire here.
Alternative: a provider picker in the console, which would let a chat-adjacent surface change
where request text is sent; provider choice stays a site decision in configuration.

### 2026-11-04 Discovery enrichment guard raised to 6 x top_n; B2 still partial at the round cap
Decision (owner): `MAX_ENRICHED_PER_TOP` goes from 5 to 6, because B2's top 10 lacked
cross-checks for three compositions at 52 enriched. One recording round
(`scripts/record_case_gaps.py B2`) added 58 public-API responses (28 Materials Project, 14
OpenAlex, 16 PubChem) and the replay has no gap left. Observed on the rerun (scripted model,
cassettes): B2 enriches 59 compositions in 12 rounds and then stops at the separate
`MAX_ENRICHMENT_ROUNDS` (12) with two newcomers per round still arriving, so the case
remains partial for that reason and the suite stays at 39 of 43 (E3, E4, G4 skipped). With
the round cap lifted on the recorded data alone, a 13th round asks for Sr2TaN3 and
Sr3(BN2)2, which are not recorded. Raising the round cap, and a second recording round, are
left to the owner; no other case's result moved.
Alternative: raise the round cap in the same change, which would move the failure a second
time without a decision on how far enrichment may run.

### 2026-11-04 The image bakes no model provider or fetch mode
Decision: the `api` Docker image and the Apptainer recipe no longer set `LLM_PROVIDER=none` or
`FETCH_MODE=replay`; only `AUTH_MODE=none` and the data cache directory are baked in, and the
Settings defaults apply (Anthropic, falling back to no model with a `missing_key` status when
no key is given; recorded data unless `FETCH_MODE` is set). A `.env` passed to the container
or to Compose therefore turns the model on, as the fresh-clone decision intends. Before this, a
Compose user with a key in `.env` still got "No model configured (LLM_PROVIDER=none)", because
the image's value stood whenever `.env` did not name the variable, and a Compose stack with
Postgres but no seeded store ran in `replay` against an empty store. The CI docker job now
asserts the provider, the missing-key status, and the help route on the bare image.
Alternative: document the two variables as things to set in `.env` for Docker, which leaves
the image contradicting the README's "model on by default".

### 2026-11-04 Run files are written atomically; a run in flight never reads its file
Decision: `RunStore.save` writes to a temp name in the same directory and renames it in one
step, and the API's status route answers an in-flight run from its state without opening the
file. Before this, a `/status` poll that landed while the worker was writing the bundle parsed
an empty file ("Invalid JSON: EOF while parsing a value"), which failed one CI run and one
local test run at random. A test writes the file 25 times under a concurrent reader.
Alternative: retry the read on a parse error, which hides the half-written file instead of
removing it.

### 2026-11-04 Requested properties are matched to criteria by phrase, in code
Decision: `config/schema.py` maps a requested property to a criterion by the exact table
first and then by an ordered phrase list (`PROPERTY_PHRASES`: "conductiv" and "thermal" name
nothing; "dielectric", "band gap", "gap", "toxic", "stab", "simple", "evidence", "public",
"deposition", "cost" and their neighbours name their criterion), and the parse response
returns both the names as typed and the criterion each was understood as. Found when the
brief's own example, parsed by Sonnet, came back with "Not available from configured sources:
dielectric, thermodynamically stable, wide band gaps, non-toxic elements": the model had
listed the request's preferences in its own words, as the prompt asks, and the exact table
did not hold those words. The run request from the web app now also carries the names (it
sent an empty list before), so the bundle marks a property no source covers. B3's "thermal
conductivity" and B4's "conductivity" stay unavailable.
Alternative: ask the model to normalize the names to the table's keys, which moves a code
decision into the prompt and breaks the next time the wording differs.

### 2026-11-04 Parse and run: one click when nothing needs confirming
Decision (owner): a "Parse and run" button starts the run as soon as the parse returns, when
the response carries no refusal, no missing field, no clamp, no unmatched name, and no
property that no source covers; otherwise the confirm form opens with a sentence naming what
stopped it. "Parse, then confirm" keeps the plan's confirm-before-fetch path, and the form
stays editable after a one-click run's parse. The button exists only when a model can parse
(`llm_status` ok). The decision reads the server's parse response; the browser decides nothing
about chemistry or settings. A progress panel with a seconds counter shows during the parse.
Alternative: always auto-run after a parse, which would start a search on clamped or partly
understood settings without the scientist seeing them.

### 2026-11-04 The rationale covers the shown rows; an oversized prompt is never sent
Decision: the rationale step asks the model only for the rows the views show (top N) and the
overview; ranked rows beyond top N keep their template text, which is verified by construction.
The loop estimates a request's input tokens (one per three characters, deliberately high)
and refuses it before sending when it exceeds what is left in the step's token budget; any
provider error other than an unavailable key or credit fails that step, never the run. Found
when a discovery run asked for one sentence per ranked row (about 1,700) and sent a
1,154,398-token prompt that the provider rejected with HTTP 400; the run failed whole and
saved nothing. With the fix the same run completes with model rationale for the top N.
Alternative: chunk the rationale across several calls for every ranked row, which spends
calls on sentences no view displays.

## Track H sweep: the brief's example, end to end

### 2026-11-04 Evidence is all-or-none across the shown rows
Decision (owner): when, after classification, some shown rows (the top N and the anchors) carry
verified labels and others with abstracts could not be classified (budget, a cache miss),
evidence leaves every row in that run and a partial reason says which rows were unread. A run
with no model, where no row has labels, is already uniform and is not affected. Found when the
brief's example put B2O3 first on a stale cached label while HfO2, ZrO2, Y2O3, La2O3 went
unread and tied at 1.000. The demo configuration becomes `CLASSIFY_MODE=live` (the Settings
default); the confirm step shows the call estimate before Run.
Alternative: keep scoring each row on whatever labels it has, which lets a lucky cache entry
decide the top of the list.

### 2026-11-04 Comparisons use cross-checked rows only
Decision (owner): a row scored on summary data alone (`enrichment_missing`: no hazard record,
structure, or literature) stays in the exports with `cross_checked: no`, and the page says how
many such rows sit beyond top N. The anchor's placement, the chart, and the overview count only
cross-checked rows. Found when SiO2 read "would place 25th of 1634, between SO2 and Sb2O3"
against molecules and acids nobody had checked.
Alternative: drop those rows from the ranking, which loses them from the exports a reviewer
uses to see what the screen did not check.

### 2026-11-04 Exclusions are counted by rule and the near misses come first
Decision: the results page counts exclusions by rule and shows cross-checked exclusions first,
then the rest by the weighted mean their kept breakdown would give (a sort key, never shown).
The chart names only shown rows and anchors among the unplotted and counts the rest. The
Caveats section defines only caveats the shown ranked rows and anchors carry.
`experimental_gap_unreferenced` is never a row's key caveat. Found on the same run: 50 of 385
exclusions shown alphabetically (Ac, As, Be compounds), a 1,600-entry unplotted list, and the
same unreferenced-table sentence as the key caveat on most rows.
Alternative: keep the alphabetical list, which shows the least relevant exclusions first.

### 2026-11-04 The rationale says "not scored" where a value exists, and explains the rank
Decision: the model's view marks a criterion that has a value but is not scored (the dielectric
band pending) as "not scored: <reason>", and a missing value as "missing: <reason>"; the step
fragment asks for why the row ranks where it does relative to its neighbours and not for the
caveats the page already shows. The model's view stays digit-free (the overview note about
summary-only rows carries no counts). Found when the rationale said "dielectric constant is
missing" beside k = 18.7.
Alternative: hide unscored criteria from the model, which leaves it unable to mention a
displayed value.

### 2026-11-04 The fake judge reads the caveats of the rows the view shows
Decision: the judge item `caveat_presence` lists the caveat ids of the shown top N and the
anchors, not every ranked row beyond top N that no view displays. The old list passed only
because the alphabetical exclusion list happened to carry the same ids; with exclusions
reordered, two cases' judge items flipped to fail on ids the page never shows. The suite stays
at 39 of 43 and no judge item changes outcome.
Alternative: keep listing every ranked row, which grades a view on text it cannot hold.

## Track H: Haiku default and the UI audit (Nov 4)

### 2026-11-04 The default model is Haiku
Decision: `LLM_MODEL` defaults to `claude-haiku-5-5` (Settings, the preset guard, `.env.example`,
the Terraform default, the cold run). The four tools are narrow (parse into a form, label one
abstract, write token prose, propose a relaxation), and code checks every output, so the
smaller model's cost and speed fit. The client sends no sampling, thinking, or prefill
parameters, so none of Haiku 5.5's request restrictions apply. The eval judge stays on Sonnet:
a judge that differs from the model under test is the stronger check. Live results recorded
on Sonnet stay as they are.
Alternative: keep Sonnet, at a higher cost per run for the same checked outputs.

### 2026-11-04 One provider failure ends classification for the run
Decision: when a classify call fails because the model is unavailable (no credit, a rejected
key) or the provider returns an error, the step stops; the remaining abstracts stay
unclassified with the same plain reason, and no further request is sent. The decision log
counts labelled calls and failed calls separately. Found on the brief's example: about thirty
identical "usage limit" lines, and a log line saying "29 classified by the model" when every
call had failed.
Alternative: keep calling per abstract, which repeats the failure and spends on a dead key.

### 2026-11-04 Reader-facing failure reasons are plain sentences
Decision: a provider error reaches the page as "provider error (BadRequestError, HTTP 400)"
or the model-status sentence; the raw provider message stays in the decision-log entry's
detail. The partial banner lists its reasons one per line.
Alternative: show the raw message, which put a Python dict on the results page.

### 2026-11-04 The evidence note names rows on the final page
Decision: when evidence is dropped, the note names the unread rows of the final top N and
anchors. Before, it named the rows of the round where the rule fired, including SO3 (later
excluded) and Li2O (pushed to 12th).
Alternative: name the rows at the time the rule fired, which names rows the page never shows.

### 2026-11-04 Sensitivity ranges use the rank the page shows
Decision: perturbed ranks are competition ranks at display precision, the rule behind "1=".
Six rows tied at 1.000 showed "rank 1 to 1", "2 to 2" ... "6 to 6" while all read "1=".
Alternative: keep positional ranks, which contradicts the table.

### 2026-11-04 The template rationale holds values, not caveats
Decision: the no-model rationale lists the row's criterion values only; the reference row
gets the same template. Before, it appended the row's caveat text, so the Why cell repeated
the Key caveat beside it, and the reference row said "no rationale (no model)".
Alternative: keep caveats in the template, which duplicates a column.

### 2026-11-04 Element symbols in the hazard policy are strings
Decision: the loader rejects a non-string element symbol, and `No` (nobelium) is quoted. YAML
1.1 reads a bare `No` as false, so the radioactive list held `False` and not nobelium.
Alternative: switch YAML loaders, a larger change for one symbol.

### 2026-11-04 Smaller page fixes from the UI audit
Decision:
- The drill-down's Source names the database and Method the aggregate.
- The band gap rule text names the JARVIS record and the MP polymorph it was matched to.
- The ECHA attribution is its own line, not a caveat bullet.
- "Band offsets" appears once, under "What this screen cannot tell you".
- The pending-reference caveat names its property.
- Molecular-exclusion details read as one parenthetical.
- Chart ticks carry no unit.
- The decision log is in time order with one score line.
- The console shows yes/no for booleans and "not set" for a layer that holds nothing.
- Compound hazard rows show their recorded PubChem codes.
- The form shows the effective hull cutoff as a hint under its input.
- The run history reads a small summary index instead of parsing every bundle.
- Wide tables scroll inside their panel on a phone.

Each change has a test (docs/FAILURE_MATRIX.md).
Alternative: none considered; these are defects.
