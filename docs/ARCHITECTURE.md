# Architecture

The thesis: the model interprets and explains; the data layer and the scorer own every
number; every guarantee lives in code; the model has no tool that could break one.

## The pipeline

```
 request text                      formulas
      |                                |
      v                                v
 [parse: model tool]  ----------> QuerySettings ---> resolve(): core > site > profile > query
      |  refusal (fixed text)                              clamps shown, config sha
      v
 confirm (scientist)
      |
      v
 fetch (code) ---- Materials Project, PubChem, OpenAlex, snapshots; or the recorded cassettes;
      |            or the Postgres store with TTLs. Every response is hashed and kept.
      v
 group by composition, match polymorphs (code)
      |
      v
 score (code) <------ enrich the top K and anchors, classify abstracts [model tool, quoted
      |               sentence checked verbatim by code], score again; repeat until the top K
      |               is enriched
      v
 relaxations counted by re-scoring (code)        rationale from tokens [model tool]
      |                                                      |
      v                                                      v
 verifier (code): every number, id, formula and quote in model text resolves to the bundle
      |
      v
 ProvenanceBundle (JSON, versioned) ---> PI view, audit view, CSV, Markdown, the web app
```

Each box names who did the work. Three steps call the model, each through one strict tool:
`parse_request`, `classify_abstract`, `write_rationale`. A fourth, `propose_relaxation`, picks
one of the relaxations code already computed, in the CLI only. Nothing the model returns is a
number, a rank, an exclusion, or a caveat trigger; the rationale tool returns template tokens
that code fills from the bundle.

## The trust boundary

| Step | Who | Reaches |
|---|---|---|
| Parse, classify, rationale, relax | model, one tool each, strict schemas | the model provider's endpoint only |
| Resolve, clamp, fetch planning, grouping, scoring, exclusions, relaxation counts, token filling, verifier, rendering | code | nothing outside the process |
| Fetch | code | Materials Project, OpenAlex, PubChem; the Postgres store |
| API and web | code | the browser; roles from the bearer token |

**Egress.** `adapters/egress.py` refuses, before sending, any host outside
`CoreConfig.allowed_hosts` plus the configured model endpoint; the transport and the model
clients both run that check. The site Compose override (`compose.site.yaml`) keeps Postgres
and Keycloak on an internal network with no outside route and puts only the API on the
egress network; the dev file publishes them on 127.0.0.1. The host allowlist itself is
enforced by the application check; a network-level domain allowlist needs an egress proxy or
a firewall with domain rules, which this repository does not include (see
`docs/ADMIN_GUIDE.md`).

**Roles** come only from the bearer token (`api/auth.py`); the model never sees a role and no
request field can change one. `docs/PERMISSIONS.md` lists every route by role and a test
checks the list against the app.

## The prefilter principle (Track F)

The discovery query to Materials Project receives only hard rules, each at the loosest value
any admissible setting could reach: the profile's PBE gap floor
(`discovery_pbe_floor_ev`), its hard gap maximum, the site's maximum hull cutoff, and the
element count. Soft preferences (the 5 eV gap start) and tighter query settings (a gap
window, a lower cutoff) are exclusions in the scorer, so excluded rows stay in the fetched
set and every relaxation proposal can say how many candidates it adds, counted by
re-scoring. `agent/pipeline.py::discovery_filter` is the one place this is applied.

## Invariants and where they live

| Invariant | Enforced in | Checked by |
|---|---|---|
| Every number traces to a source record | `records.Provenance` on every `Value`; the bundle index | `tests/scoring/test_golden_bundle.py`, `tests/verify` |
| Missing is `None` with a reason, never a default | `records.Value` validator; `x or default` is banned | adapter tests with exact-zero, "na", and absent fields |
| Scores, ranks, exclusions, caveats are computed | `scoring/`; the model tools return no numbers | `tests/scoring`, `tests/agent/test_tools.py` |
| The model has no state-changing tool | `agent/tools.py` has four read-only tools | `tests/agent/test_tools.py`, evals F5, F6 |
| Only approved public sources | `adapters/egress.py` | `tests/adapters/test_egress.py` |
| Nothing in chat changes roles or config | `api/auth.py`; config is files reviewed in git | `tests/api/test_auth.py`, evals F1, F2, F11 |
| Model text passes the verifier before display | `verify/verifier.py`; `render.markdown.render` refuses an unverified model run | `tests/verify`, `tests/render` |
| Same settings, byte-identical prompts; deterministic ties | prompt hashes per step; the rank key `(-total, composition, mp id)` | `tests/agent/test_prompts.py`, `tests/scoring/test_scorer.py` |

## Determinism and replay

- `config_sha`: a hash of the resolved configuration, in every bundle.
- `prompt_hash`: a hash of the prompt fragments, the tool schemas, and the fragment set
  version, per step and per run.
- `source_versions`: the Materials Project database version and the snapshot hashes.
- `bundle_version`: the bundle contract (2); new fields default so old bundles still load.
- `materials-triage replay RUN_ID` re-ranks a stored run from stored data with no network.
- `materials-triage diff RUN_A RUN_B` attributes every rank change to the candidate set,
  data (a source version moved), config, model (an evidence label changed), or displacement.
  Evidence labels are cached by abstract hash, prompt hash, and model version, so a rerun with
  the same model reuses them.

What may vary between runs: the parse (fixed once the scientist confirms), evidence labels
when the model is live, and rationale wording. Everything after the parse is deterministic for
a given bundle, and the eval suite's G1 case checks five repeats are identical in ranks,
exclusions, and prompt hash.

## Where things live

| Package | Role |
|---|---|
| `adapters/` | call planning and parsing per source, the transport with rate limits and retries, the egress check, the store-backed runner |
| `records/` | the data models, the bundle contract, grouping, polymorph matching, structural dimensionality |
| `config/` | the four layers, `resolve()`, clamps, the config sha |
| `scoring/` | the deterministic scorer, criteria, hazard and band gap policies, strict config loaders |
| `agent/` | the model tools and steps, the pipeline, relaxation counting |
| `verify/` | the verifier |
| `render/` | view models, Markdown templates, CSV, caveat text resolution, the glossary |
| `api/` | the HTTP API, auth, the run manager, the console helpers |
| `cli/` | the command line, wiring, run files, the run diff |
| `web/` | the browser app; it formats nothing |
| `evals/`, `validation/` | the eval harness and the validation study behind `docs/EVAL.md` |
