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

## Track C: API and web

## Track D: deploy and docs

## Track E: eval and validation
