# CLAUDE.md

Project: materials-triage. An agentic assistant that triages candidate materials
for a materials-science research center, built as a take-home for Lila Sciences.
Full plan: internal/PLAN_OVERVIEW.md. Read it before planning any work.

## The thesis (every design choice must serve it)

The LLM interprets and explains. The data layer and the scorer own every number.
Every guarantee lives in code. The agent has no tool that could break one.

## Invariants (never violate; flag any task that would)

1. Every number shown to a user traces to a source record ID in the provenance store.
2. Missing data is marked missing. Never fill, estimate, or predict a value.
3. Scores, ranks, exclusions, and caveat triggers are computed by code, never by the LLM.
4. The agent has no tools for wetlab actions, private data, writes to config, or
   arbitrary web fetches. Do not add any.
5. Data comes only from the approved public APIs and versioned snapshots listed in
   the plan. No scraping. No paywalled sources.
6. Nothing typed in chat changes roles, permissions, or configuration.
7. LLM output that cites a record or a number passes the verifier before display.
   Evidence quotes must match the source abstract verbatim.
8. Same settings produce byte-identical prompts. Ties in ranking break deterministically.

## How we work

- Plan before code. For any non-trivial change, propose the approach, the files,
  and the tests first, and wait for approval.
- Small steps. One concern per change. Tests land with or before the code.
- Explain every choice. The owner must defend every line in a final-round review.
  When you choose between alternatives, record it in docs/DECISIONS.md:
  decision, reason, alternative considered.
- The wire is the truth, the docs are a hypothesis. Record real API responses
  before writing adapters or fakes. Build fixtures from recordings, not from docs.
- Read back every write. Never report something as done, configured, or passing
  until you have checked it. Unverified claims never go in docs.
- If prompt changes move a failure instead of removing it, move the logic into code.
- Ask when unsure. Do not guess at chemistry, API behavior, or requirements.
  Say "unverified" rather than state something you have not checked.

## Chemistry claims

Do not write chemistry claims into code, prompts, or docs on your own authority.
Caveat text, thresholds, and hazard tiers come from config files whose entries cite
a public source. If a caveat needs a fact, leave a TODO naming the fact to be
sourced, and tell the owner.

## Stack

- Backend: Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Postgres, pymatgen.
- Agent: Anthropic SDK tool-use loop, written directly. No agent framework.
  Model version is pinned in config. Provider switchable to Bedrock by config.
- Frontend: Vite, React, TypeScript. Types generated from the FastAPI OpenAPI schema.
  Three screens only: workspace, provenance drill-down, admin/FDE console.
- Auth: Keycloak (OIDC) in Compose with a seeded realm. Local no-auth mode for dev.
- Deploy: Docker Compose (primary). Terraform AWS reference module (optional, late).
- Tests: pytest, vcrpy recorded fixtures, golden-file tests for prompts and views.
- CI: lint (ruff), types (mypy, tsc), tests, gitleaks.

## Conventions

- No emojis anywhere: code, comments, docs, commit messages, UI text.
- Docs: plain short sentences, present tense, end state only ("the system does X").
- Secrets only via environment variables. Never commit keys. .env.example lists them.
- Commit messages: imperative, one line summary, body explains why.
- Iteration notes, grader findings, and planning files live in internal/ (gitignored).

## Commands

Only commands that work are listed.

- `uv sync` installs everything (Python 3.12 via `.python-version`).
- `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`
  is what CI runs.
- `docker compose up -d` starts Postgres 16; `docker compose exec postgres pg_isready -U triage`
  checks it.
- `uv run python scripts/record_wire.py --mode once --sources pubchem,oqmd,mp,openalex,cod`
  records live responses into `fixtures/wire/`; `--mode none` replays with no network. MP and
  OpenAlex read their keys from `.env`.
- `uv run python scripts/fetch_snapshots.py` downloads the JARVIS and matbench files into
  `.data-cache/` and writes slices plus `fixtures/snapshots/MANIFEST.json`.
