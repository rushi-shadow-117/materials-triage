# materials-triage

An assistant that triages candidate materials before experiments. It pulls from public
sources only (Materials Project, JARVIS-DFT, an experimental band gap dataset, OpenAlex,
PubChem, COD), scores candidates with code, and uses a language model only to interpret
the request and explain the result. Every number traces to a source record.

Status: Phase 1 (data layer): adapters for every source, a normalized record model, and an
append-only Postgres provenance store with cache and replay modes. Not yet runnable as a
product. See `docs/` for decisions and wire findings.

## Run the app

```
uv sync
cp .env.example .env            # keys only for live fetch or a live model
cd web && npm ci && npm run build && cd ..
uv run materials-triage serve   # http://127.0.0.1:8000, API and web app in one process
```

With `LLM_PROVIDER=none` (the development default in tests) the Describe box says parsing
needs a model; fill the criteria form by hand or use Rank my list. Data, scoring,
verification and both views are real, from the recorded cassettes when Postgres is not
reachable (`--fetch auto`).

Demo configuration, one parse call per Describe request and no classification calls:

```
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-5-5
CLASSIFY_MODE=cache_only
ANTHROPIC_API_KEY=...
```

`CLASSIFY_MODE=cache_only` reads evidence labels from the classifier cache and marks misses
unclassified; it never calls the model for an abstract. Auth: `AUTH_MODE=none` locally (the
role is `DEV_ROLE`), `static` with `STATIC_TOKENS=token:role,...`, or `oidc` (Keycloak:
`docker compose --profile auth up -d keycloak`). Roles and permissions: `docs/PERMISSIONS.md`.
Browser tests: `uv run playwright install chromium && uv run pytest -q -m e2e`.

