#!/usr/bin/env bash
# Cold run: a fresh clone, no keys, no database, no model. Checks the install, the web build,
# the served API and app, one Rank my list run over the API, and one eval case.
#   bash scripts/cold_run.sh /tmp/cold-run [git-ref]
# Every step prints PASS or FAIL; the first FAIL stops the run with exit status 1. No Anthropic
# call. Run it alone: step 4's tests use the local Postgres when one answers, and two test
# sessions against one database empty each other's tables.
set -uo pipefail

# A step is a function; run_step prints its label, then PASS, or FAIL and exit 1. Each step
# runs in a subshell with errexit, so any failing command in it fails the step (a plain
# `a && b && echo PASS` printed nothing and carried on when `a` failed).
run_step() {
  printf '%-48s' "$1"
  # not inside `if`: bash ignores errexit in a condition, even in a subshell
  (set -e; "$2")
  local rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "PASS"
  else
    echo "FAIL"
    exit 1
  fi
}

if [ "${COLD_RUN_HELPERS_ONLY:-}" = 1 ]; then
  return 0 2>/dev/null || exit 0
fi

# a developer shell may export the parent checkout's virtualenv; the clone has its own
unset VIRTUAL_ENV
DEST="${1:?destination directory}"
REF="${2:-HEAD}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${COLD_RUN_PORT:-8765}"
SERVE_PID=""
trap '[ -n "$SERVE_PID" ] && kill "$SERVE_PID" 2>/dev/null || true' EXIT

clone() {
  rm -rf "$DEST"
  git clone -q "$SRC" "$DEST"
  git -C "$DEST" checkout -q "$REF"
}

sync() { (cd "$DEST" && uv sync -q --frozen); }

web() { (cd "$DEST/web" && npm ci --no-audit --no-fund >/dev/null 2>&1 && npm run build >/dev/null 2>&1); }

checks() {
  cd "$DEST"
  uv run ruff check -q .
  uv run mypy src >/dev/null
  uv run pytest -q -p no:cacheprovider -m "not e2e and not keycloak" >/dev/null
}

serve() {
  cd "$DEST"
  for i in $(seq 1 90); do
    curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
    sleep 2
  done
  curl -fsS "http://127.0.0.1:$PORT/api/health" | python3 -c '
import json,sys; h=json.load(sys.stdin)
assert h["fetch_source"]=="cassettes", h; assert h["llm_status"]=="missing_key", h
assert h["llm_model"]=="claude-haiku-5-5", h; assert "fill the criteria form" in h["llm_note"], h'
}

app_routes() {
  [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/")" = 200 ]
  [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/console")" = 200 ]
}

rank_list() {
  local run status
  run=$(curl -fsS -X POST "http://127.0.0.1:$PORT/api/runs" -H 'Content-Type: application/json' \
    -d '{"request_text":"cold run","profile":"oxide_dielectric_thin_film","settings":{"mode":"candidate_list","candidate_list":["HfO2","ZrO2","Al2O3","Unobtainium oxide"]}}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')
  for i in $(seq 1 120); do
    status=$(curl -fsS "http://127.0.0.1:$PORT/api/runs/$run/status" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
    [ "$status" = "completed" ] && break
    [ "$status" = "failed" ] && return 1
    sleep 1
  done
  [ "$status" = "completed" ]
  curl -fsS "http://127.0.0.1:$PORT/api/runs/$run/view?view=pi_summary" | python3 -c '
import json,sys; v=json.load(sys.stdin)
rows=[r["composition"] for r in v["rows"]]; assert rows==["Al2O3","HfO2","ZrO2"], rows
assert v["unresolved_candidates"]==["Unobtainium oxide"]; assert [a["composition"] for a in v["anchors"]]==["SiO2"]
assert "mp-" not in json.dumps(v["rows"])'
  curl -fsS -H 'Accept: text/html' "http://127.0.0.1:$PORT/runs/$run" | grep -q '<div id="root">'
  curl -fsS -H 'Accept: text/html' "http://127.0.0.1:$PORT/runs" | grep -q '<div id="root">'
}

eval_case() {
  cd "$DEST"
  uv run python -m evals run --suite F1 --out "$DEST/.cold-evals" 2>/dev/null \
    | grep -q 'F1: pass_rate=1.00'
}

run_step "1. clone $REF into $DEST" clone
run_step "2. uv sync (locked)" sync
run_step "3. web: npm ci and build" web
run_step "4. lint, types, unit tests (no browser)" checks

# The defaults, nothing else: no .env in a fresh clone, and no setting passed. Keys a
# developer shell exports are cleared so this is the fresh machine the README describes.
cd "$DEST"
env -u ANTHROPIC_API_KEY -u LLM_PROVIDER -u LLM_MODEL -u CLASSIFY_MODE -u FETCH_MODE \
  -u DATABASE_URL -u AUTH_MODE -u MP_API_KEY -u OPENALEX_API_KEY \
  nohup uv run materials-triage serve --port "$PORT" > serve.log 2>&1 &
SERVE_PID=$!
run_step "5. bare serve on :$PORT (defaults only)" serve
run_step "6. the web app answers at / and /console" app_routes
run_step "7. Rank my list over the API; its page reloads" rank_list
run_step "8. one eval case on the scripted model (F1)" eval_case

echo "cold run complete: $DEST"
