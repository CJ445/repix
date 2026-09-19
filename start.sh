#!/usr/bin/env bash
# Start Repix with Docker Compose.
#
# Checks Docker, .env, port availability, image and container state first, then does the
# least work needed: build only what's missing, start only what isn't running, and wait
# until the stack actually answers requests.
#
#   ./start.sh            start (builds images only if they don't exist yet)
#   ./start.sh --build    rebuild images first (use after pulling code changes)
#   ./start.sh --logs     follow logs after starting
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

FRONTEND_PORT=5173
BACKEND_PORT=8000
HEALTH_TIMEOUT=180

FORCE_BUILD=0
FOLLOW_LOGS=0

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; BOLD=""; RESET=""
fi
info() { echo "${BOLD}==>${RESET} $*"; }
ok()   { echo "${GREEN}✔${RESET} $*"; }
warn() { echo "${YELLOW}!${RESET} $*" >&2; }
die()  { echo "${RED}✖${RESET} $*" >&2; exit 1; }

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"; }

for arg in "$@"; do
  case "$arg" in
    --build) FORCE_BUILD=1 ;;
    --logs)  FOLLOW_LOGS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "Unknown option: $arg" ;;
  esac
done

# ---- Prerequisites -----------------------------------------------------------------
command -v docker >/dev/null 2>&1 || die "Docker is not installed. See https://docs.docker.com/get-docker/"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required ('docker compose' not found)."
docker info >/dev/null 2>&1 || die "Docker is installed but the daemon isn't reachable. Start Docker (or check your permissions) and retry."

if [ ! -f .env ]; then
  [ -f .env.example ] || die ".env is missing and there is no .env.example to copy from."
  cp .env.example .env
  ok "Created .env from .env.example"
fi

compose() { docker compose "$@"; }
services() { compose config --services | grep -v '^$'; }

running_services() { compose ps --status running --services 2>/dev/null | grep -v '^$' || true; }
is_running() { running_services | grep -qx "$1"; }

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$port" 2>/dev/null | tail -n +2 | grep -q .
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1  # can't tell; let Docker report any conflict
  fi
}

# ---- Container state ---------------------------------------------------------------
mapfile -t ALL_SERVICES < <(services)
mapfile -t RUNNING < <(running_services)

if [ "${#RUNNING[@]}" -eq "${#ALL_SERVICES[@]}" ] && [ "$FORCE_BUILD" -eq 0 ]; then
  ok "Already running: ${RUNNING[*]}"
  ALREADY_UP=1
else
  ALREADY_UP=0
  if [ "${#RUNNING[@]}" -gt 0 ] && [ "$FORCE_BUILD" -eq 0 ]; then
    info "Partially running (${RUNNING[*]}); bringing up the rest"
  fi
fi

# ---- Ports (only matter for services we're about to start) -------------------------
if [ "$ALREADY_UP" -eq 0 ]; then
  is_running frontend || ! port_in_use "$FRONTEND_PORT" || die "Port $FRONTEND_PORT is already in use by another process."
  is_running backend  || ! port_in_use "$BACKEND_PORT"  || die "Port $BACKEND_PORT is already in use by another process."
fi

# ---- Images ------------------------------------------------------------------------
if [ "$ALREADY_UP" -eq 0 ]; then
  MISSING=()
  while read -r image; do
    [ -n "$image" ] || continue
    docker image inspect "$image" >/dev/null 2>&1 || MISSING+=("$image")
  done < <(compose config --images)

  if [ "$FORCE_BUILD" -eq 1 ]; then
    info "Rebuilding images (--build)…"
    compose build
  elif [ "${#MISSING[@]}" -gt 0 ]; then
    info "Image(s) not built yet: ${MISSING[*]} — building (first build downloads the AI models, ~590 MB)…"
    compose build
  else
    ok "Images present (use --build to rebuild after code changes)"
  fi

  info "Starting containers…"
  compose up -d --no-build
fi

# ---- Wait until it's actually serving ----------------------------------------------
wait_for_backend() {
  local cid status
  cid="$(compose ps -q backend)"
  [ -n "$cid" ] || return 1
  for ((i = 0; i < HEALTH_TIMEOUT; i += 2)); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo gone)"
    case "$status" in
      healthy) return 0 ;;
      none)    curl -fsS "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1 && return 0 ;;
      gone)    return 1 ;;
    esac
    [ "$(docker inspect --format '{{.State.Running}}' "$cid" 2>/dev/null)" = "true" ] || return 1
    sleep 2
  done
  return 1
}

info "Waiting for the backend to become healthy (up to ${HEALTH_TIMEOUT}s)…"
if ! wait_for_backend; then
  warn "Backend did not become healthy. Last log lines:"
  compose logs --tail 30 backend >&2 || true
  die "Startup failed. Fix the error above and re-run, or inspect with: docker compose logs -f"
fi

if command -v curl >/dev/null 2>&1; then
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    curl -fsS -o /dev/null "http://localhost:$FRONTEND_PORT/" 2>/dev/null && break
    sleep 1
  done
  curl -fsS -o /dev/null "http://localhost:$FRONTEND_PORT/" 2>/dev/null || die "Frontend isn't responding on port $FRONTEND_PORT."
fi

if curl -fsS "http://localhost:$BACKEND_PORT/ready" >/dev/null 2>&1; then
  ok "AI models loaded"
else
  warn "Backend is up but AI models aren't loaded — colorize/upscale will be unavailable (see: docker compose logs backend)."
fi

echo
ok "${BOLD}Repix is running${RESET}"
echo "   App:  http://localhost:$FRONTEND_PORT"
echo "   API:  http://localhost:$BACKEND_PORT"
echo "   Stop: ./stop.sh"

if [ "$FOLLOW_LOGS" -eq 1 ]; then
  echo
  exec docker compose logs -f
fi
