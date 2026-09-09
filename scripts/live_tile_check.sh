#!/usr/bin/env bash
# Cold shell to a verified NDVI tile URL, in one command.
#
#     ./scripts/live_tile_check.sh
#
# `check_real_ndvi.py` calls Earth Engine directly, which answers "is Earth
# Engine working". It does not answer "does the endpoint the browser calls
# return a tile URL", and that is the question standing between this and a
# client demo. This starts the backend, calls `POST /api/tile/ndvi` over HTTP
# exactly as the page does, prints the URL that came back, and stops.
#
# Run it, not `source` it: it changes nothing about your shell.
#
#     --mock   run against mock_ee_backend, no credentials needed. Proves the
#              plumbing — the server, the route, the request shape, the JSON —
#              so that a failure without it is Earth Engine and nothing else.
#     --keep   leave the backend running afterwards, to open the page against.
#     --year   which year to ask for (default: last complete one).
#
# Exit codes are the interface, as everywhere in this project:
#     0  a real tile URL came back
#     3  never got as far as asking — no credentials, or the server never came up
#     4  asked, and the answer was not a usable tile URL

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
MOCK=0
KEEP=0
YEAR="$(( $(date +%Y) - 1 ))"

while [ $# -gt 0 ]; do
  case "$1" in
    --mock) MOCK=1 ;;
    --keep) KEEP=1 ;;
    --year) YEAR="$2"; shift ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '%s\n' "$*"; }
PY="${PYTHON:-python3}"
[ -x "$REPO/venv/bin/python" ] && PY="$REPO/venv/bin/python"

# --- the environment -------------------------------------------------------
#
# Sourced in a subshell would be pointless, so this script is deliberately the
# thing you run *after* `source setup.sh` — or instead of remembering to. The
# check below is the whole reason this exists: it says which of the two things
# is missing, rather than letting uvicorn fail with a stack trace.
if [ "$MOCK" -eq 0 ]; then
  if [ -z "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" ] || [ -z "${EE_PROJECT:-}" ]; then
    say "The Earth Engine environment is not loaded in this shell."
    say
    say "    source ./setup.sh"
    say
    say "Or, to check everything except Earth Engine itself:"
    say
    say "    ./scripts/live_tile_check.sh --mock"
    say
    say "To stop needing to remember:  ./scripts/install_shell_hook.sh"
    exit 3
  fi
  APP="app:app"
  WHAT="Earth Engine (project ${EE_PROJECT})"
else
  APP="mock_ee_backend:app"
  WHAT="the mock backend — no credentials, no Earth Engine"
fi

# --- start it --------------------------------------------------------------
say "Backend:  $APP"
say "Serving:  $WHAT"
say "Asking:   POST http://127.0.0.1:${PORT}/api/tile/ndvi  {\"year\": ${YEAR}}"
say

LOG="$(mktemp)"
( cd "$REPO" && "$PY" -m uvicorn "$APP" --port "$PORT" --log-level warning ) \
  > "$LOG" 2>&1 &
SERVER=$!

cleanup() {
  if [ "$KEEP" -eq 1 ] && [ "${OK:-0}" -eq 1 ]; then
    say
    say "Backend still running on :${PORT} (pid ${SERVER}). Stop it with: kill ${SERVER}"
    return
  fi
  kill "$SERVER" 2>/dev/null
  wait "$SERVER" 2>/dev/null
}
trap cleanup EXIT

# Wait for the port rather than sleeping a guessed number of seconds. Earth
# Engine's first import is slow, and a fixed sleep is either a flaky failure or
# wasted time on every run.
for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/" 2>/dev/null; then
    UP=1; break
  fi
  kill -0 "$SERVER" 2>/dev/null || break
  sleep 1
done

if [ "${UP:-0}" -ne 1 ]; then
  say "✗ The backend never came up."
  say
  sed 's/^/    /' "$LOG" | tail -25
  exit 3
fi

# --- ask -------------------------------------------------------------------
BODY="$(curl -sS -X POST "http://127.0.0.1:${PORT}/api/tile/ndvi" \
        -H 'Content-Type: application/json' \
        -d "{\"year\": ${YEAR}}" -w '\n%{http_code}' 2>&1)"
CODE="$(printf '%s' "$BODY" | tail -n1)"
JSON="$(printf '%s' "$BODY" | sed '$d')"

if [ "$CODE" != "200" ]; then
  say "✗ HTTP ${CODE}"
  say
  printf '%s\n' "$JSON" | sed 's/^/    /'
  say
  say "That is the endpoint answering, so the server and the route are fine."
  say "Whatever is in the detail above came from Earth Engine."
  exit 4
fi

URL="$("$PY" - "$JSON" <<'EOF'
import json, sys
try:
    print(json.loads(sys.argv[1]).get("tile_url_template", ""))
except Exception:
    print("")
EOF
)"

# A tile template with no {x}/{y}/{z} is not a tile template, however well the
# request went. Checking the shape rather than trusting a 200 is the same rule
# the rest of this project applies to a provider's response.
case "$URL" in
  *"{x}"*"{y}"*|*"{z}"*)
    OK=1
    say "✓ A real tile URL came back."
    say
    say "    ${URL}"
    say
    if [ "$MOCK" -eq 1 ]; then
      say "That was the mock. The server, the route, the request shape and the"
      say "JSON contract all work — so if the real run fails, it is Earth"
      say "Engine and nothing else."
    else
      say "That is a live Earth Engine tile URL for ${YEAR}."
      say "Open site-scanner.html and the badge should read 'Live Earth Engine'."
    fi
    exit 0
    ;;
  "")
    say "✗ 200, but no tile_url_template in the response:"
    printf '%s\n' "$JSON" | sed 's/^/    /'
    exit 4
    ;;
  *)
    say "✗ 200, but that is not an XYZ tile template — no {x}/{y}/{z} in it:"
    say "    ${URL}"
    exit 4
    ;;
esac
