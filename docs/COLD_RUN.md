# Cold run

What a fresh machine needs and what it should see. `scripts/cold_run.sh` runs the whole
list on a fresh clone with no keys, no database, and no model, and prints PASS or FAIL per
step. It makes no model call.

## Prerequisites

- Python 3.12 and `uv` (`uv sync` installs everything from the lock file).
- Node 20 and npm (the web build).
- Optional: Docker (Postgres, Keycloak, the images), Playwright Chromium for the browser
  tests (`uv run playwright install chromium`).

## The checklist

1. Clone and `uv sync --frozen`.
2. `cd web && npm ci && npm run build`.
3. `uv run ruff check .`, `uv run mypy src`, `uv run pytest -q -m "not e2e and not keycloak"`.
4. `uv run materials-triage serve` with no keys; `/api/health` reports `fetch_source: cassettes`.
5. `/` and `/console` answer 200 (the app routes).
6. Rank my list over the API for HfO2, ZrO2, Al2O3, Unobtainium oxide: Al2O3, HfO2, ZrO2
   ranked in that order, SiO2 as the anchor, the fourth name reported as not found, and no
   record id in the PI view.
7. One eval case on the scripted model: `uv run python -m evals run --suite A1` passes.

```
bash scripts/cold_run.sh /tmp/cold-run        # defaults to the current commit
```

## Last recorded run

Recorded below by Track D from the commit it was run on; rerun the script to refresh.

<!-- cold-run-output -->
Commit d0f7a2a, 2026-11-03, macOS, Python 3.12, Node 20, `bash scripts/cold_run.sh <dir> HEAD`:

```
1. clone HEAD into /private/tmp/claude-501/-Users-rpate-Desktop-lila/b0df2d3a-4f11-40e2-83f8-e15d6537bdd7/scratchpad/cold-run2PASS
2. uv sync (locked)                             PASS
3. web: npm ci and build                        PASS
4. lint, types, unit tests (no browser, no db)  PASS
5. serve on :8765 from recorded data            PASS
6. the web app answers at / and /console        PASS
7. Rank my list over the API                    PASS
8. one eval case on the scripted model (A1)     PASS
cold run complete: /private/tmp/claude-501/-Users-rpate-Desktop-lila/b0df2d3a-4f11-40e2-83f8-e15d6537bdd7/scratchpad/cold-run2
exit=0
```
<!-- /cold-run-output -->
