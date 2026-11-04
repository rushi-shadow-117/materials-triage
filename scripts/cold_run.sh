#!/usr/bin/env bash
# Cold run: a fresh clone, no keys, no database, no model. Checks the install, the web build,
# the served API and app, one Rank my list run over the API, and one eval case.
#   bash scripts/cold_run.sh /tmp/cold-run [git-ref]
# Prints PASS or FAIL per step and exits non-zero on the first failure. No Anthropic call.
set -euo pipefail
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

step "5. serve on :$PORT from recorded data"
LLM_PROVIDER=none AUTH_MODE=none FETCH_MODE=replay DATABASE_URL="postgresql+psycopg://x:x@127.0.0.1:1/x" \
  nohup uv run materials-triage serve --port "$PORT" > serve.log 2>&1 &
SERVE_PID=$!
trap 'kill $SERVE_PID 2>/dev/null || true' EXIT
for i in $(seq 1 90); do curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break; sleep 2; done
curl -fsS "http://127.0.0.1:$PORT/health" | grep -q '"fetch_source":"cassettes"' && ok

step "6. the web app answers at / and /console"
[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/")" = 200 ] \
  && [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/console")" = 200 ] && ok

step "7. Rank my list over the API"
RUN=$(curl -fsS -X POST "http://127.0.0.1:$PORT/runs" -H 'Content-Type: application/json' \
  -d '{"request_text":"cold run","profile":"oxide_dielectric_thin_film","settings":{"mode":"candidate_list","candidate_list":["HfO2","ZrO2","Al2O3","Unobtainium oxide"]}}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')
for i in $(seq 1 120); do
  S=$(curl -fsS "http://127.0.0.1:$PORT/runs/$RUN/status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  [ "$S" = "completed" ] && break; [ "$S" = "failed" ] && { echo "FAIL ($S)"; exit 1; }; sleep 1
done
curl -fsS "http://127.0.0.1:$PORT/runs/$RUN/view?view=pi_summary" | python3 -c '
import json,sys; v=json.load(sys.stdin)
rows=[r["composition"] for r in v["rows"]]; assert rows==["Al2O3","HfO2","ZrO2"], rows
assert v["unresolved_candidates"]==["Unobtainium oxide"]; assert [a["composition"] for a in v["anchors"]]==["SiO2"]
assert "mp-" not in json.dumps(v["rows"])' && ok

step "8. one eval case on the scripted model (A1)"
uv run python -m evals run --suite A1 --out "$DEST/.cold-evals" 2>/dev/null | grep -q 'A1: pass_rate=1.00' && ok

echo "cold run complete: $DEST"
