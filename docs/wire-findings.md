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
- No key holds a Materials Project ID. There is an `icsd` key. Matching to MP is by
  reduced composition plus space group number, as planned; there is no ID to cross-check.
- Unverified: the sentinel used for missing values (JARVIS uses the string `"na"` in some
  releases). Check per field before treating a value as numeric.

## matbench_expt_gap (file snapshot)

- Source: `https://ml.materialsproject.org/projects/matbench_expt_gap.json.gz`, the URL in
  matminer's `dataset_metadata.json`. 37,200 bytes. SHA256
  `783e7d14...ca75b2` matches the hash matminer publishes.
- Pandas "split" layout: `{"columns": ["composition", "gap expt"], "index": [...], "data": [...]}`.
  4,604 rows. 2,450 rows (53%) have a gap of exactly 0. Those are the Materials Project DFT
  metals, not measurements; the nonzero-only rule stands.
- Composition-level only. No structure, no polymorph. Values attach to the composition group.
- 7 of 11 compositions present: BeO 10.39, HfO2 5.55, La2O3 5.4, Ta2O5 4.2, TiO2 3.3,
  Y2O3 5.6, ZrO2 4.99 (eV). Absent: Al2O3, SiO2, ThO2, BaTiO3. There is no row with those
  element sets in any stoichiometry except three Ba-Ti-O rows at other ratios, all zero.
  So the "best available" band gap policy falls through to TBmBJ or PBE for four of the
  eleven, including the SiO2 anchor and Al2O3, which the normal eval expects near the top.
- Differs from plan: the plan assumed experimental coverage for the common oxides. It is
  patchy even for them. The row must show the band gap source every time.

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
- Consequences for the hazard policy: GHS data is per compound and per notifier, with
  particle-form effects (SiO2 and TiO2 carry inhalation and carcinogenicity codes that
  refer to respirable dust, not to a thin film). It cannot be the primary hazard signal.
  The element-level policy stays primary; GHS appears as a secondary signal with the
  notifier counts shown. Radioactivity (ThO2) does not appear in GHS at all.
- Rate limit held at about 4 requests per second with a 0.25 s pause; no 503 seen.

## COD (OPTIMADE)

- Base URL confirmed from the OPTIMADE providers index: `https://www.crystallography.net/cod/optimade`.
- Unreachable on 2026-10-31 from this network: TCP connect timeouts on every request,
  including the COD homepage, over both https and http. DNS resolves (158.129.170.82). Whether
  this is a COD outage or a network block on this side is unknown. `fixtures/wire/cod/meta.json`
  records the errors; no cassettes exist yet. Retry on Nov 1. If it stays unreachable, the
  Phase 1 decision on COD as a core source has to account for availability.

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
