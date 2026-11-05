#!/usr/bin/env bash
# Cold run: a fresh clone, no keys, no database, no model. Checks the install, the web build,
# the served API and app, one Rank my list run over the API, and one eval case.
#   bash scripts/cold_run.sh /tmp/cold-run [git-ref]
# Prints PASS or FAIL per step and exits non-zero on the first failure. No Anthropic call.
set -euo pipefail
# a developer shell may export the parent checkout's virtualenv; the clone has its own
unset VIRTUAL_ENV
DEST="${1:?destination directory}"
REF="${2:-HEAD}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${COLD_RUN_PORT:-8765}"
step() { printf '%-48s' "$1"; }
ok() { echo "PASS"; }

step "1. clone $REF into $DEST"
rm -rf "$DEST" && git clone -q "$SRC" "$DEST" && git -C "$DEST" checkout -q "$REF" && ok
cd "$DEST"

step "2. uv sync (locked)"
uv sync -q --frozen && ok

step "3. web: npm ci and build"
(cd web && npm ci --no-audit --no-fund >/dev/null 2>&1 && npm run build >/dev/null 2>&1) && ok

step "4. lint, types, unit tests (no browser, no db)"
uv run ruff check -q . && uv run mypy src >/dev/null && uv run pytest -q -p no:cacheprovider -m "not e2e and not keycloak" >/dev/null && ok

step "5. bare serve on :$PORT (defaults only)"
# The defaults, nothing else: no .env in a fresh clone, and no setting passed. Keys a
# developer shell exports are cleared so this is the fresh machine the README describes.
env -u ANTHROPIC_API_KEY -u LLM_PROVIDER -u LLM_MODEL -u CLASSIFY_MODE -u FETCH_MODE \
  -u DATABASE_URL -u AUTH_MODE -u MP_API_KEY -u OPENALEX_API_KEY \
  nohup uv run materials-triage serve --port "$PORT" > serve.log 2>&1 &
SERVE_PID=$!
trap 'kill $SERVE_PID 2>/dev/null || true' EXIT
for i in $(seq 1 90); do curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break; sleep 2; done
curl -fsS "http://127.0.0.1:$PORT/api/health" | python3 -c '
import json,sys; h=json.load(sys.stdin)
assert h["fetch_source"]=="cassettes", h; assert h["llm_status"]=="missing_key", h
assert h["llm_model"]=="claude-haiku-5-5", h; assert "fill the criteria form" in h["llm_note"], h' && ok

step "6. the web app answers at / and /console"
[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/")" = 200 ] \
  && [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/console")" = 200 ] && ok

step "7. Rank my list over the API; its page reloads"
RUN=$(curl -fsS -X POST "http://127.0.0.1:$PORT/api/runs" -H 'Content-Type: application/json' \
  -d '{"request_text":"cold run","profile":"oxide_dielectric_thin_film","settings":{"mode":"candidate_list","candidate_list":["HfO2","ZrO2","Al2O3","Unobtainium oxide"]}}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')
for i in $(seq 1 120); do
  S=$(curl -fsS "http://127.0.0.1:$PORT/api/runs/$RUN/status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  [ "$S" = "completed" ] && break; [ "$S" = "failed" ] && { echo "FAIL ($S)"; exit 1; }; sleep 1
done
curl -fsS "http://127.0.0.1:$PORT/api/runs/$RUN/view?view=pi_summary" | python3 -c '
import json,sys; v=json.load(sys.stdin)
rows=[r["composition"] for r in v["rows"]]; assert rows==["Al2O3","HfO2","ZrO2"], rows
assert v["unresolved_candidates"]==["Unobtainium oxide"]; assert [a["composition"] for a in v["anchors"]]==["SiO2"]
assert "mp-" not in json.dumps(v["rows"])' \
  && curl -fsS -H 'Accept: text/html' "http://127.0.0.1:$PORT/runs/$RUN" | grep -q '<div id="root">' \
  && curl -fsS -H 'Accept: text/html' "http://127.0.0.1:$PORT/runs" | grep -q '<div id="root">' && ok

step "8. one eval case on the scripted model (A1)"
uv run python -m evals run --suite A1 --out "$DEST/.cold-evals" 2>/dev/null | grep -q 'A1: pass_rate=1.00' && ok

echo "cold run complete: $DEST"
