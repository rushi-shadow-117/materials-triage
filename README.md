# materials-triage

An assistant that triages candidate materials for a research center before anyone spends
deposition time. A scientist describes what they want, or pastes a list of formulas; the
tool returns a ranked shortlist with exclusions, caveats, and the data it could not find,
and every number on the page links to the public record it came from.

The model interprets and explains. Code owns every number: scores, ranks, exclusions, and
caveat triggers are computed from recorded source data, and the model's text is checked
against the data before it is shown. The model has four tools (parse a request, classify an
abstract, write rationale from tokens, pick a code-computed relaxation) and none of them
changes anything.

Design note: `docs/DESIGN_NOTE.md` (added separately).

## Run it in five minutes

Needs Python 3.12 with [uv](https://docs.astral.sh/uv/) and Node 20. No keys and no database:
the recorded data in `fixtures/` serves every source.

```
git clone <this repo> && cd materials-triage
uv sync
cd web && npm ci && npm run build && cd ..
uv run materials-triage serve
```

Open http://127.0.0.1:8000, choose Rank my list, paste `HfO2, ZrO2, Al2O3, Unobtainium oxide`,
review the criteria, and run. The command line does the same:

```
uv run materials-triage rank --formulas HfO2,ZrO2,Al2O3 --no-llm --fetch cassettes
```

The brief's discovery request runs offline with no key from a criteria file:

```
uv run materials-triage query "Find promising oxide dielectric candidates for thin-film experiments." \
  --yes --no-llm --criteria examples/brief_discovery.yaml --fetch cassettes
```

Or with Docker: `docker build --target api -t materials-triage:api . && docker run --rm -p 8000:8000 materials-triage:api`.

The bare defaults read the recorded data and use `claude-haiku-5-5`. With no key, a banner
says there is no model and the criteria form is filled by hand; a rejected key or an empty
credit balance does the same. `scripts/cold_run.sh` runs this whole check on a fresh clone.

## The demo configuration

With a key, the model is on by default: it parses Describe requests and classifies
abstracts (`CLASSIFY_MODE=live`), and the confirm step shows the run's estimated model calls
before it runs: for the brief's example, one parse call, up to 50 classify calls (five
abstracts each for the top 10, fewer when labels are cached), and one rationale call. In `.env`:

```
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-5-5
ANTHROPIC_API_KEY=...
CLASSIFY_MODE=live
```

`CLASSIFY_MODE=cache_only` reads evidence labels from the classifier cache only and never calls
the model for an abstract; when that leaves some shown rows labelled and others unread, evidence
is dropped for every row in the run and the page says so. `LLM_PROVIDER=openai` and `gemini`
are experimental presets (own key, explicit `LLM_MODEL`; not evaluated), see
`docs/ADMIN_GUIDE.md`. Live fetching needs `FETCH_MODE=live`,
`MP_API_KEY`, and `OPENALEX_API_KEY` plus Postgres (`docker compose up -d`, then `uv run alembic
upgrade head`); with `FETCH_MODE` unset, or without Postgres, runs use the recorded data and
say so.

## Sign-in

`AUTH_MODE=none` (the default, development only; refused with `SITE_MODE=true`) gives every
request the role in `DEV_ROLE`, and a role switcher in the app's header tries each of the
three roles. `static` reads
bearer tokens from `STATIC_TOKENS=token:role,...`. `oidc` validates JWTs from an identity
provider; `docker compose --profile auth up -d keycloak` starts one with three dev users,
`scientist`, `fde`, and `admin`, whose passwords equal their names. Roles come only from the
token. See `docs/PERMISSIONS.md` for what each role may do.

## What goes where

| Data | Goes to |
|---|---|
| Request text, candidate formulas, abstracts of matched papers, a token-only view of the ranking | the configured model provider |
| Formulas and search terms | Materials Project, PubChem, OpenAlex (the only hosts the app can reach) |
| Run bundles, the classifier cache, the audit log | `DATA_CACHE_DIR` on the API host |
| Raw source responses | the Postgres store, when one is configured |

Deployment accounts never accept the Materials Project GNoME license: documents under the
BY-NC license are dropped at the adapter and never scored.

## Guides

- `docs/SCIENTIST_GUIDE.md`: using the workspace and reading a result. Both guides are also
  on the app's Help page, and every screen has a "How to use this screen" panel.
- `docs/ADMIN_GUIDE.md`: install, settings, sign-in, the console, refresh, egress, backups.
- `docs/CONFIGURING.md`: the four configuration layers and how to add a scoring profile.
- `docs/DATA_SOURCES.md`: every source, its license, and what is recorded.
- `docs/ARCHITECTURE.md`: the pipeline, the trust boundary, determinism and replay.
- `docs/DISCOVERY_QUESTIONS.md`: what the tool leaves to the scientist.
- `docs/EXTENSIONS.md`: what is not built and how it would attach.
- `docs/COLD_RUN.md`: the fresh-machine checklist and its last recorded run.
- `docs/DECISIONS.md`, `docs/FAILURE_MATRIX.md`, `docs/EVAL.md`: every design decision with
  its alternative, every guarded failure with its test, and the evaluation report.

## Commands

```
uv run materials-triage --help                 # query, rank, replay, diff, export, serve, eval
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q
uv run python -m evals run --suite all        # scripted model, recorded data, no API call
uv run python scripts/generate_eval_report.py
```

Tests run against recorded data and a scripted model; nothing in the test suite calls a
model provider. Browser tests need `uv run playwright install chromium`.
