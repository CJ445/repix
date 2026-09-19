#!/usr/bin/env bash
# Stop Repix (Image Lab).
#
#   ./stop.sh            stop the containers (keeps them and the images; fastest restart)
#   ./stop.sh --down     stop and remove the containers (images are kept)
#   ./stop.sh --purge    stop, remove containers AND built images (asks first; add -y to skip)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

MODE=stop
ASSUME_YES=0

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
    --down)  MODE=down ;;
    --purge) MODE=purge ;;
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "Unknown option: $arg" ;;
  esac
done

command -v docker >/dev/null 2>&1 || die "Docker is not installed."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required ('docker compose' not found)."
docker info >/dev/null 2>&1 || die "Docker daemon isn't reachable, so there's nothing for this script to stop."

# .env is only needed for variable interpolation; compose refuses to parse without it.
[ -f .env ] || { [ -f .env.example ] && cp .env.example .env; }

mapfile -t EXISTING < <(docker compose ps -a --services 2>/dev/null | grep -v '^$' || true)
mapfile -t RUNNING < <(docker compose ps --status running --services 2>/dev/null | grep -v '^$' || true)

if [ "${#EXISTING[@]}" -eq 0 ]; then
  ok "No Repix containers exist — nothing to stop."
elif [ "$MODE" = stop ]; then
  if [ "${#RUNNING[@]}" -eq 0 ]; then
    ok "Already stopped."
  else
    info "Stopping: ${RUNNING[*]}…"
    docker compose stop
    ok "Stopped. Start again with ./start.sh"
  fi
else
  info "Removing containers…"
  docker compose down --remove-orphans
  ok "Containers removed."
fi

if [ "$MODE" = purge ]; then
  IMAGES=()
  while read -r image; do
    [ -n "$image" ] && docker image inspect "$image" >/dev/null 2>&1 && IMAGES+=("$image")
  done < <(docker compose config --images)

  if [ "${#IMAGES[@]}" -eq 0 ]; then
    ok "No built images to remove."
  else
    if [ "$ASSUME_YES" -eq 0 ]; then
      warn "This deletes: ${IMAGES[*]}"
      warn "The next ./start.sh will rebuild them (re-downloads the AI models if they aren't cached)."
      read -r -p "Continue? [y/N] " reply
      [[ "$reply" =~ ^[Yy]$ ]] || { echo "Cancelled; images kept."; exit 0; }
    fi
    docker image rm "${IMAGES[@]}"
    ok "Images removed."
  fi
fi
