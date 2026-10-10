#!/usr/bin/env bash
# One command to start the whole WhoSaid demo on macOS.
#
#   scripts/demo.sh            Docker, AgntID runtime, Ollama (optional), tool server, API, frontend; opens the dashboard
#   scripts/demo.sh --mock     frontend only, on built-in mock data (no Docker, runtime, tool server or API)
#   scripts/demo.sh --live     dashboard runs call the live model instead of replaying the committed fixture
#   scripts/demo.sh --detach   start everything, then return (no Ctrl+C handling; stop with scripts/stop.sh)
#   scripts/demo.sh --no-open  do not open the browser
#
# Idempotent: a healthy service on its port is reused. Ctrl+C (or scripts/stop.sh) stops the tool server, API and
# vite. The AgntID runtime keeps running unless stop.sh gets --all. Logs and PID files live in logs/ (gitignored).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$ROOT/logs"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PY="$BACKEND/.venv/bin/python"
RUNTIME_DIR="${AGNTID_RUNTIME_DIR:-$HOME/agntid-runtime}"

TOOL_PORT=8765
API_PORT=8000
WEB_PORT="${DEMO_WEB_PORT:-5173}"   # overridable for testing
OLLAMA_PORT=11434

MOCK=0 LIVE=0 DETACH=0 OPEN=1
for arg in "$@"; do
  case "$arg" in
    --mock) MOCK=1 ;;
    --live) LIVE=1 ;;
    --detach) DETACH=1 ;;
    --no-open) OPEN=0 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

mkdir -p "$LOGS"

# ---- output helpers --------------------------------------------------------------------------------
if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; D=$'\033[2m'; N=$'\033[0m'; else B='' G='' R='' Y='' D='' N=''; fi
say()  { printf '%s==>%s %s\n' "$B" "$N" "$*"; }
warn() { printf '%swarning:%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%serror:%s %s\n' "$R" "$N" "$*" >&2; exit 1; }

ROWS=()   # "service|url|status|note"
row() { ROWS+=("$1|$2|$3|${4:-}"); }

# ---- helpers ---------------------------------------------------------------------------------------
http_ok() { curl -fsS -m 3 "$1" >/dev/null 2>&1; }

wait_for() {  # description, timeout_seconds, command...
  local timeout="$2"; shift 2
  local waited=0
  until "$@" >/dev/null 2>&1; do
    waited=$((waited + 1))
    [ "$waited" -le "$timeout" ] || return 1
    sleep 1
  done
}

port_holder() { lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {printf "%s (pid %s, user %s)\n", $1, $2, $3}' | sort -u | head -3; }

fail_port_busy() {  # name port
  local holder; holder="$(port_holder "$2")"
  die "port $2 (needed by $1) is taken by something that is not a healthy $1:
${holder:-  (could not identify the process)}
Stop it (kill <pid>) or free the port, then run scripts/demo.sh again."
}

start_bg() {  # name, workdir, command...   (extra env is inherited from the caller)
  local name="$1" dir="$2"; shift 2
  : > "$LOGS/$name.log"
  # exec: the recorded PID is the real process, and nothing keeps this script's stdout open
  ( cd "$dir" && exec nohup "$@" >>"$LOGS/$name.log" 2>&1 </dev/null ) &
  echo $! >"$LOGS/$name.pid"
}

cleanup() {
  trap - INT TERM EXIT
  echo
  say "stopping the tool server, API and frontend (the AgntID runtime keeps running)"
  "$ROOT/scripts/stop.sh" || true
  exit 0
}

# ---- 1. Docker -------------------------------------------------------------------------------------
if [ "$MOCK" = 0 ]; then
  say "Docker"
  command -v docker >/dev/null 2>&1 || die "docker is not installed (Docker Desktop is required for the AgntID runtime)"
  if ! docker info >/dev/null 2>&1; then
    echo "  Docker Desktop is not running; starting it..."
    open -a Docker || die "could not start Docker Desktop (open -a Docker failed)"
    wait_for "docker" 120 docker info || die "Docker did not become ready within 120s. Open Docker Desktop manually and check it, then retry."
  fi
  row "Docker" "-" "OK"

  # ---- 2. AgntID runtime ---------------------------------------------------------------------------
  say "AgntID runtime (${RUNTIME_DIR/#$HOME/~})"
  [ -f "$RUNTIME_DIR/docker-compose.yml" ] || die "no docker-compose.yml in $RUNTIME_DIR. Set it up first (see policies/README.md) or set AGNTID_RUNTIME_DIR."
  (cd "$RUNTIME_DIR" && docker compose up -d >"$LOGS/runtime-compose.log" 2>&1) \
    || die "docker compose up failed in $RUNTIME_DIR; see logs/runtime-compose.log"
  runtime_healthy() {
    local out; out="$(cd "$RUNTIME_DIR" && docker compose ps --format '{{.Service}}={{.Health}}' 2>/dev/null)"
    [ "$(printf '%s\n' "$out" | grep -c '=healthy')" -ge 2 ]
  }
  wait_for "runtime" 240 runtime_healthy || die "the AgntID runtime did not become healthy within 240s (first start downloads a ~900 MB model). Check: cd $RUNTIME_DIR && docker compose ps && docker compose logs --tail 50"
  http_ok "http://localhost:8080/health" || die "the runtime reports healthy but http://localhost:8080/health does not answer"
  row "AgntID runtime" "http://localhost:8082/mcp" "OK" "UI http://localhost:8080"

  # ---- 3. Ollama (optional) ------------------------------------------------------------------------
  say "Ollama"
  if http_ok "http://localhost:$OLLAMA_PORT/api/version"; then
    row "Ollama" "http://localhost:$OLLAMA_PORT" "OK" "already running"
  elif command -v ollama >/dev/null 2>&1; then
    start_bg ollama "$ROOT" ollama serve
    if wait_for "ollama" 20 http_ok "http://localhost:$OLLAMA_PORT/api/version"; then
      row "Ollama" "http://localhost:$OLLAMA_PORT" "OK" "started"
    else
      rm -f "$LOGS/ollama.pid"
      warn "Ollama did not start (see logs/ollama.log). Fine for the fixture demo; --live needs it."
      row "Ollama" "http://localhost:$OLLAMA_PORT" "WARN" "down; the demo replays from the fixture"
    fi
  else
    warn "Ollama is not installed. Fine for the fixture demo; --live needs it."
    row "Ollama" "-" "WARN" "not installed"
  fi
  if [ "$LIVE" = 1 ] && ! http_ok "http://localhost:$OLLAMA_PORT/api/version"; then
    die "--live needs Ollama, which is not running (logs/ollama.log)"
  fi

  # ---- 4. Tool server, then API --------------------------------------------------------------------
  [ -x "$PY" ] || die "backend virtualenv missing at backend/.venv. Create it: cd backend && uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e '.[dev]'"
  [ -f "$BACKEND/.env" ] || die "backend/.env is missing. Copy backend/.env.example and fill it in (the tool-server secrets)."

  say "Tool server (:$TOOL_PORT)"
  tool_healthy() { curl -fsS -m 3 "http://127.0.0.1:$TOOL_PORT/_admin/health" 2>/dev/null | grep -q '"ok":true'; }
  if tool_healthy; then
    row "Tool server" "http://127.0.0.1:$TOOL_PORT" "OK" "reused"
  else
    [ -z "$(port_holder "$TOOL_PORT")" ] || fail_port_busy "tool server" "$TOOL_PORT"
    start_bg tool-server "$BACKEND" "$PY" -W ignore -m whosaid.mcp_server
    wait_for "tool server" 60 tool_healthy || die "the tool server did not become healthy within 60s; see logs/tool-server.log"
    row "Tool server" "http://127.0.0.1:$TOOL_PORT" "OK" "started"
  fi

  say "API (:$API_PORT)"
  api_healthy() { curl -fsS -m 3 "http://127.0.0.1:$API_PORT/health" 2>/dev/null | grep -q '"ok":true'; }
  if api_healthy; then
    row "API" "http://localhost:$API_PORT" "OK" "reused"
    [ "$LIVE" = 0 ] || warn "the API was already running, so --live only applies if it was started with it (stop it with scripts/stop.sh first)"
  else
    [ -z "$(port_holder "$API_PORT")" ] || fail_port_busy "API" "$API_PORT"
    if [ "$LIVE" = 1 ]; then export DEFAULT_LIVE=true; fi
    start_bg api "$BACKEND" "$PY" -W ignore -m whosaid.api
    wait_for "API" 60 api_healthy || die "the API did not become healthy within 60s; see logs/api.log"
    row "API" "http://localhost:$API_PORT" "OK" "started$([ "$LIVE" = 1 ] && echo ', live model')"
  fi

  # the API's own view: is the tool server healthy and the AgntID runtime reachable?
  health="$(curl -fsS -m 5 "http://127.0.0.1:$API_PORT/health")"
  report="$(printf '%s' "$health" | python3 -c "
import json, sys
h = json.load(sys.stdin)
print('tool_server=%s' % ('ok' if h['tool_server']['healthy'] else 'FAIL'))
print('agntid=%s' % ('ok' if h['agntid']['reachable'] else 'FAIL'))
")"
  printf '%s\n' "$report" | grep -q 'tool_server=ok' || die "the API cannot reach the tool server (see logs/api.log)"
  printf '%s\n' "$report" | grep -q 'agntid=ok' || die "the API cannot reach the AgntID runtime at its MCP endpoint (see logs/api.log)"
  row "API -> tool server" "-" "OK"
  row "API -> AgntID" "-" "OK"
fi

# ---- 5. Frontend -----------------------------------------------------------------------------------
say "Frontend (:$WEB_PORT)"
[ -d "$FRONTEND/node_modules" ] || die "frontend dependencies are missing. Run: cd frontend && npm install"
web_up() { curl -sS -m 3 -o /dev/null "http://localhost:$WEB_PORT" 2>/dev/null; }
WANT_MODE=$([ "$MOCK" = 1 ] && echo mock || echo real)
if web_up && [ -f "$LOGS/frontend.pid" ] && [ "$(cat "$LOGS/frontend.mode" 2>/dev/null || true)" != "$WANT_MODE" ]; then
  say "frontend is running in $(cat "$LOGS/frontend.mode" 2>/dev/null || echo unknown) mode; restarting it in $WANT_MODE mode"
  fpid="$(cat "$LOGS/frontend.pid")"; pkill -TERM -P "$fpid" 2>/dev/null || true; kill -TERM "$fpid" 2>/dev/null || true; rm -f "$LOGS/frontend.pid"
  for _ in 1 2 3 4 5 6 7 8 9 10; do web_up || break; sleep 0.5; done
fi
if web_up; then
  note="reused"; [ -f "$LOGS/frontend.pid" ] || note="reused (not started by demo.sh; mode unknown)"
  row "Frontend" "http://localhost:$WEB_PORT" "OK" "$note"
else
  [ -z "$(port_holder "$WEB_PORT")" ] || fail_port_busy "frontend (vite)" "$WEB_PORT"
  # Process env beats .env.local, so the mode is set here without editing any file.
  if [ "$MOCK" = 1 ]; then export VITE_USE_MOCK=true; else export VITE_USE_MOCK=false VITE_API_URL="http://localhost:$API_PORT"; fi
  VITE_BIN="$FRONTEND/node_modules/.bin/vite"
  if [ -x "$VITE_BIN" ]; then start_bg frontend "$FRONTEND" "$VITE_BIN" --port "$WEB_PORT" --strictPort
  else start_bg frontend "$FRONTEND" npx vite --port "$WEB_PORT" --strictPort; fi
  echo "$WANT_MODE" >"$LOGS/frontend.mode"
  wait_for "frontend" 60 web_up || die "vite did not answer on port $WEB_PORT within 60s; see logs/frontend.log"
  row "Frontend" "http://localhost:$WEB_PORT" "OK" "started, $([ "$MOCK" = 1 ] && echo 'mock data' || echo 'real API')"
fi

# ---- 6. Reset, open --------------------------------------------------------------------------------
if [ "$MOCK" = 0 ]; then
  code="$(curl -sS -m 10 -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$API_PORT/reset" || echo 000)"
  case "$code" in
    204) row "Reset" "POST /reset" "OK" "demo starts clean" ;;
    409) row "Reset" "POST /reset" "WARN" "a run is in progress; left as is" ;;
    *)   row "Reset" "POST /reset" "FAIL" "HTTP $code"; die "POST /reset returned HTTP $code" ;;
  esac
fi
[ "$OPEN" = 0 ] || open "http://localhost:$WEB_PORT" >/dev/null 2>&1 || warn "could not open the browser; go to http://localhost:$WEB_PORT"

# ---- 7. Status table -------------------------------------------------------------------------------
echo
printf '%s%-22s %-32s %-6s %s%s\n' "$B" "SERVICE" "URL" "STATUS" "NOTE" "$N"
for r in "${ROWS[@]}"; do
  IFS='|' read -r svc url st note <<<"$r"
  case "$st" in OK) c="$G" ;; WARN) c="$Y" ;; *) c="$R" ;; esac
  printf '%-22s %-32s %s%-6s%s %s%s%s\n' "$svc" "$url" "$c" "$st" "$N" "$D" "$note" "$N"
done
echo
printf 'Dashboard: %shttp://localhost:%s%s\n' "$B" "$WEB_PORT" "$N"
echo "Logs: logs/*.log   Stop: scripts/stop.sh (add --all to stop the AgntID runtime too)"

if [ "$DETACH" = 1 ]; then
  exit 0
fi
trap cleanup INT TERM
echo "Running. Press Ctrl+C to stop the tool server, API and frontend."
while true; do sleep 3600 & wait $! || true; done
