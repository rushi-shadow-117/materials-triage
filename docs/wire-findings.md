# Wire findings

What each upstream source actually returns, as recorded on 2026-10-31 in `fixtures/wire/`
(vcrpy cassettes) and `fixtures/snapshots/` (file slices) for eleven oxides: HfO2, Al2O3,
ZrO2, SiO2, TiO2, ThO2, La2O3, BaTiO3, BeO, Y2O3, Ta2O5. Each section gives the endpoint
used, what was observed, and what differs from the documentation or from the plan's
assumptions. Anything not observed is marked unverified.

Recording status per material is in `fixtures/wire/<source>/meta.json`. Replay with
`uv run python scripts/record_wire.py --mode none` serves every recorded source from
cassettes with no network; PubChem and OQMD pass that replay.

## Materials Project

Unverified: no API key yet. Nothing recorded. To confirm on the first keyed run: the exact
summary field names (`energy_above_hull`, `band_gap`, `theoretical`, `deprecated`), which
functional produced each value and whether the summary document exposes it, the database
version string, dielectric endpoint coverage for the eleven oxides, extra hosts the
`mp-api` client contacts, and whether a deprecated entry can be fetched by ID.

## JARVIS-DFT dft_3d (file snapshot)

- Source: figshare file 38521619, the URL `jarvis-tools` uses for the `dft_3d` key.
  Zip of 40,811,489 bytes containing `jdft_3d-12-12-2022.json`. SHA256 in
  `fixtures/snapshots/MANIFEST.json`. The full file stays in the gitignored cache.
- 75,993 entries. 205 match one of the eleven reduced compositions. The slice is
  `fixtures/snapshots/jarvis_dft_3d.slice.json`.
- 64 keys per record. The ones this project needs: `jid`, `formula`, `spg_number`,
  `spg_symbol`, `func`, `ehull`, `formation_energy_peratom`, `optb88vdw_bandgap`,
  `mbj_bandgap`, `hse_gap`, `epsx`/`epsy`/`epsz` (OptB88vdW dielectric),
  `mepsx`/`mepsy`/`mepsz` (TBmBJ dielectric), `dfpt_piezo_max_dielectric` and its
  `_electronic`/`_ionic` parts, `icsd`, `atoms`.
- No key holds a Materials Project ID. The `icsd` key is a string on every record: empty on
  80 of the 205 slice records, a single ID on most of the rest, and on some a comma-separated
  list of dozens of IDs. 125 of 205 slice records carry at least one ICSD ID. Matching to MP:
  intersect the parsed ICSD set with the ICSD IDs in MP's `database_IDs` (field presence and
  shape unverified until a key exists); fall back to reduced composition plus space group number.
- Missing values are the string `"na"`, not null. In the slice, 42 of the 64 fields use it,
  including `mbj_bandgap`, `hse_gap`, `epsx`/`epsy`/`epsz`, `mepsx`/`mepsy`/`mepsz`, and the DFPT
  dielectric fields. The adapter maps `"na"` to missing and never to zero. `spg_number` is a
  string too.

## Experimental band gaps: expt_gap compendium and matbench_expt_gap (file snapshots)

Two tables, both derived from Zhuo, Mansouri Tehrani, Brgoch (2018), both downloaded from the
URLs in matminer's `dataset_metadata.json`, both with SHA256 matching the hash matminer publishes.

| Table | Rows | Zero-gap rows | Of 11 oxides present | Slice |
|---|---|---|---|---|
| `expt_gap` (full compendium, figshare 13464434) | 6,354 | 2,458 | 9 | `fixtures/snapshots/expt_gap.slice.json` |
| `matbench_expt_gap` (deduplicated benchmark) | 4,604 | 2,450 | 7 | `fixtures/snapshots/matbench_expt_gap.slice.json` |

- Layout for both: pandas "split" orient. Composition column is `formula` in the compendium and
  `composition` in matbench; the gap column is `gap expt` (eV) in both.
- Zero-gap rows are the Materials Project DFT metals, not measurements. Nonzero-only stands.
- Both tables are composition-level. No structure, no polymorph. Values attach to the
  composition group.
- Per-composition values in the compendium (count, min, median, max, eV), from `MANIFEST.json`:
  BaTiO3 5 values 2.96 / 3.06 / 3.13; ThO2 2 values 3.30 / 3.40 / 3.50; BeO 1 value 10.39;
  HfO2 1 value 5.55; La2O3 1 value 5.40; Ta2O5 1 value 4.20; TiO2 1 value 3.30; Y2O3 1 value 5.60;
  ZrO2 1 value 4.99. Matbench keeps the same single values and drops BaTiO3 and ThO2.
- Dedup hypothesis (matbench removed compositions whose reported gaps span more than 0.1 eV):
  confirmed for BaTiO3 (span 0.17 eV) and ThO2 (span 0.20 eV), which exist in the compendium
  with several values and are absent from matbench. Not the explanation for Al2O3 and SiO2:
  neither appears in the compendium at any stoichiometry, so they were never in the source
  compilation. The SiO2 anchor and Al2O3 have no experimental gap in either table.
- Consequences: the product reads the compendium and shows the measured range per composition
  with the count of values ("reported X to Y eV across N values"), and matbench is kept only
  for validation calibration. For Al2O3 and SiO2 the band gap policy falls through to TBmBJ or
  PBE and the row says so. If the owner wants experimental anchor values for those two, they
  come from a cited public source entered in config, not from these tables.
- The compendium carries no per-row reference. matminer's maintainers describe its provenance
  as "a bunch of different studies". Values shown from it should carry that caveat, and the
  scorer's aggregate rule (median shown with range, or minimum) is an open decision for Phase 2.

## OpenAlex

Unverified: no API key yet. Nothing recorded. To confirm: key enforcement and the daily
credit budget, the `/rate-limit` endpoint, abstract coverage for oxide dielectric papers,
and how formula strings match against a one-word synonym ("hafnia").

## PubChem

- Endpoints (all HTTP 200 for all eleven):
  - `GET /rest/pug/compound/fastformula/{formula}/cids/JSON` (formula lookup). Confirmed to
    exist. Returns 2 to 7 CIDs per formula (hydrates, isotopologues, charged forms).
  - `GET /rest/pug/compound/name/{common name}/cids/JSON` (name lookup). Returned exactly one
    CID for every one of the eleven names.
  - `GET /rest/pug_view/data/compound/{cid}/JSON?heading=GHS+Classification`. The `heading`
    parameter works and returns only that section, inside `Record > Section > ...`,
    with text in `String` fields.
- CID choice rule as recorded: the single CID from the name lookup, else the smallest CID from
  the formula lookup. Both lookups are in the cassette so the rule can change later.
- GHS content is an aggregate of company notifications, not a single classification. For
  each compound PubChem reports "N of M companies" and may say "Not Classified" alongside
  hazard statements from a minority of notifiers. Observed H-codes (minority notifications
  included):
  - No H-codes, "Not Classified" by most notifiers: HfO2 (337 of 344), ZrO2, Ta2O5, BaTiO3.
  - Al2O3: H335, H372. La2O3: H315, H319, H335. Y2O3: H315, H319, H320, H335, H413.
  - TiO2: H319, H320, H335, H351, H372, H413. SiO2: nine codes including H350, H372.
  - ThO2: H301, H311, H331, H350, H373. BeO: thirteen codes including H330, H350, H370.
- The record is per compound and per notifier, and the notifications disagree. For example
  HfO2 is reported as not meeting GHS criteria by 337 of 344 notifiers with 4 notifications
  from the other 7; ZrO2 by 1040 of 1116. The split must be shown as "hazard codes in M of N
  notifications" and never collapsed into "safe" by majority. A compound with any hazard code in
  any notification is never shown as unclassified. The adapter parses the "N of M" counts and
  keeps the raw strings.
- Several of the recorded codes concern respirable particulates (for example H335, H350i, H372
  on SiO2 and TiO2). Whether and how those apply to a given lab's thin-film process is a
  chemistry and safety judgment that belongs to the owner's sourced hazard policy, not to this
  note. The planned handling is a process-hazard flag: keep the material, attach a caveat whose
  text and source are configured by the owner. TODO for the owner: source the caveat text for
  particulate hazards in deposition work (powders, sputter targets, chamber cleaning).
- GHS says nothing about radioactivity: ThO2's record lists toxicity codes only. The
  element-level policy stays primary; GHS is a secondary, per-compound signal.
- Rate limit held at about 4 requests per second with a 0.25 s pause; no 503 seen.

## COD (OPTIMADE)

- Base URL confirmed from the OPTIMADE providers index: `https://www.crystallography.net/cod/optimade`.
- Unreachable throughout 2026-10-31 from this network (see Availability events). Nothing
  recorded. `fixtures/wire/cod/meta.json` holds the errors. Retry daily during Phase 1; decide at
  the end of Phase 1 whether COD stays a core source or becomes optional behind MP's
  `theoretical` flag. The outage is the working example for the health page and for results
  labeled partial.

## OQMD (OPTIMADE)

- Base URL `https://oqmd.org/optimade/v1`. Reports `api_version` 1.2.0 (the plan said COD
  is at 1.1.0; versions differ per provider).
- `/info/structures` lists 34 properties. Provider-specific ones: `_oqmd_stability`,
  `_oqmd_delta_e`, `_oqmd_band_gap`, `_oqmd_spacegroup`, `_oqmd_prototype`, `_oqmd_icsd_id`,
  `_oqmd_entry_id`, `_oqmd_calculation_id`, `_oqmd_volume`. Standard ones include
  `chemical_formula_reduced`, `space_group_it_number`, `nsites`, `last_modified`.
- Filter `chemical_formula_reduced="O2Ti"` works. Alphabetical element order is required:
  ZrO2 is `O2Zr`, BaTiO3 is `BaO3Ti`, Y2O3 is `O3Y2`. `scripts/record_wire.py` has
  `optimade_formula()` for this.
- Counts (`data_returned`) per composition: SiO2 204, TiO2 56, ZrO2 43, BaTiO3 40, Al2O3 26,
  HfO2 24, Y2O3 15, BeO 13, La2O3 9, Ta2O5 9, ThO2 8. With `page_limit=10`, eight of eleven
  set `more_data_available: true`. The adapter has to paginate or filter further
  (for example by `_oqmd_stability` or `space_group_it_number`).
- Response time: 1 to 5 seconds normally; the SiO2 query (204 entries) hit a 60 s read timeout
  once and succeeded on retry. Adapter timeouts must be generous and the cache must be used.

## Cross-cutting

- Three formula notations are now in play: pretty (HfO2), OPTIMADE alphabetical (O2Hf is
  wrong, HfO2 is right because H sorts before O; but TiO2 is O2Ti), and PubChem's common
  name. The normalized record model needs one canonical key (pymatgen reduced formula) and
  must store the source's own identifier beside it.
- `vcrpy` with `httpx` recorded and replayed both REST sources cleanly. The `mp-api` client
  uses `requests`; replay through the same library is unverified until a key exists.
- The httpx default timeout did not stop a hung connection to COD inside the first run; an
  explicit `httpx.Timeout(connect=15, read=120)` did. Adapters must set explicit timeouts.

## Availability events

| Date (UTC) | Source | Symptom | Outcome |
|---|---|---|---|
| 2026-10-31 17:25 to 17:45 | COD | TCP connect timeout on every request to www.crystallography.net (OPTIMADE, homepage, http and https). DNS resolved to 158.129.170.82. | Nothing recorded. Cause unknown (COD outage or network block on this side). |
| 2026-10-31 17:53 | COD | Same, one retry. | Same. Retry daily. |
| 2026-10-31 17:30 | OQMD | Read timeout after 60 s on the SiO2 query (204 entries). | Succeeded on retry with a 120 s read timeout. |
