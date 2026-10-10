#!/usr/bin/env bash
# Stop what scripts/demo.sh started: the tool server, the API and vite (tracked by PID files in logs/).
# The AgntID runtime (Docker) keeps running unless you pass --all.
#
#   scripts/stop.sh          stop tool server, API, vite
#   scripts/stop.sh --all    also stop the AgntID runtime containers (and Ollama if demo.sh started it)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$ROOT/logs"
RUNTIME_DIR="${AGNTID_RUNTIME_DIR:-$HOME/agntid-runtime}"
ALL=0
for arg in "$@"; do
  case "$arg" in
    --all) ALL=1 ;;
    -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

stopped=()

stop_pidfile() {  # name
  local name="$1" file="$LOGS/$1.pid" pid
  [ -f "$file" ] || return 0
  pid="$(cat "$file" 2>/dev/null || true)"
  rm -f "$file"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    pkill -TERM -P "$pid" 2>/dev/null || true   # children first (npx/vite spawn node)
    kill -TERM "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; sleep 0.3; done
    if kill -0 "$pid" 2>/dev/null; then
      pkill -KILL -P "$pid" 2>/dev/null || true
      kill -KILL "$pid" 2>/dev/null || true
    fi
    stopped+=("$name")
  fi
}

mkdir -p "$LOGS"
stop_pidfile frontend
rm -f "$LOGS/frontend.mode"
stop_pidfile api
stop_pidfile tool-server

if [ "$ALL" = 1 ]; then
  stop_pidfile ollama
  if [ -f "$RUNTIME_DIR/docker-compose.yml" ] && docker info >/dev/null 2>&1; then
    (cd "$RUNTIME_DIR" && docker compose stop >/dev/null 2>&1) && stopped+=("agntid-runtime")
  fi
fi

if [ "${#stopped[@]}" -eq 0 ]; then
  echo "nothing to stop (no running services tracked in $LOGS)"
else
  echo "stopped: ${stopped[*]}"
fi
[ "$ALL" = 1 ] || echo "(the AgntID runtime is still running; use --all to stop it too)"
