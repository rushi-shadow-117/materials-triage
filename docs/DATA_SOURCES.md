# Data sources

Only these sources, only through the adapters in `src/materials_triage/adapters/`. No
scraping, no paywalled sources, no full text. `docs/wire-findings.md` records what each API
actually returned when it was first recorded.

| Source | What it provides | Access | Auth | License and handling | Cache TTL |
|---|---|---|---|---|---|
| Materials Project (`api.materialsproject.org`) | polymorphs with PBE band gap, energy above the mixed GGA/GGA+U/R2SCAN hull per functional, dielectric constants, crystal structures; the discovery query | REST, paged, ceiling 10,000 documents | `MP_API_KEY` | per-document license from `builder_meta`; `BY-NC` (GNoME) documents dropped; deprecated documents dropped | 7 days |
| JARVIS-DFT 3D | TBmBJ band gaps matched to MP polymorphs (ICSD id first, then composition and space group) | pinned snapshot `jdft_3d-12-12-2022`, sha256 `d4c64660e9e1…`, 75,993 rows; the committed slice covers the baseline oxides | none | JARVIS terms; `na` is missing, never 0 | never (pinned) |
| Experimental gap compendium (`expt_gap`) | measured band gaps by composition | pinned snapshot, sha256 `2d0980e3533c…`, 6,354 rows; zero gaps excluded as metals | none | the product's experimental source | never |
| matbench_expt_gap | the same, used for validation only | pinned snapshot, sha256 `783e7d1461eb…`, 4,604 rows | none | validation, never scoring | never |
| OpenAlex (`api.openalex.org`) | abstracts of papers matching "{formula} thin film", title and abstract scope, five per candidate | REST | `OPENALEX_API_KEY`, `OPENALEX_MAILTO` | open; quotes are verified against the stored abstract | 30 days |
| PubChem (`pubchem.ncbi.nlm.nih.gov`) | compound id by name and formula, GHS hazard statements as "codes in M of N notifications", synonyms | PUG REST and PUG View | none | open; rows citing ECHA show the attribution line | 90 days |
| Config reference values | owner-entered experimental values with citation and material form | `config/reference_values.yaml` | none | entered entries only | never |

Cut after recording: OQMD (HTTP 502 on every structures query) and COD (wired, recorded,
not used by the pipeline). AFLOW was never a source.

## What is recorded

`fixtures/adapters/<source>/*.yaml` holds the recorded HTTP interactions, keyed by the call's
canonical URL and parameters, with keys and mail parameters stripped. `CassetteFetch` serves
them with no database and no network; it is the test, CI, and offline-demo path. Recorded:
88 compositions (summary, thermo, dielectric, structure, OpenAlex search, PubChem), the
discovery queries each profile sends, and the extra calls every eval case makes
(`scripts/record_case_gaps.py`, two live rounds at most per case).
`fixtures/adapters/recording_manifest.json` lists what was recorded and when.

## What goes to the model provider

Only when a provider is configured: the request text (parse), the abstracts of matched
papers one at a time (classify), and a token-only view of the ranking (rationale). Never a
key, never private data, never the raw source responses. `CLASSIFY_MODE=cache_only` stops
the abstract calls.

## Provenance

Every value carries the source, record id, raw response hash, fetch time, and source version;
the Postgres store keeps the raw responses so a number can be traced after the source changes.
The Materials Project database version is read from the heartbeat on every run and recorded in
the bundle; a version change invalidates the cache for that source.
