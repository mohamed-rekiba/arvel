#!/usr/bin/env bash
# Wait until the given docker compose services report `healthy`, with a spinner.
# A service whose container defines no healthcheck is treated as ready.
#
# Usage: healthcheck.sh [service ...]   (defaults to: db redis backend frontend)
# Env:   COMPOSE      docker compose invocation (default: "docker compose")
#        WAIT_TIMEOUT seconds before giving up   (default: 300)
set -euo pipefail

COMPOSE="${COMPOSE:-docker compose}"
TIMEOUT="${WAIT_TIMEOUT:-300}"

services=("$@")
[ ${#services[@]} -eq 0 ] && services=(db redis backend frontend)

# Echo a service's docker health status, or a sentinel when it isn't running yet.
health() {
  local cid status
  cid="$($COMPOSE ps -q "$1" 2>/dev/null || true)"
  if [ -z "$cid" ]; then
    echo "not-started"
    return
  fi
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$cid" 2>/dev/null || true)"
  echo "${status:-unknown}"
}

spin='|/-\'
i=0
start="$(date +%s)"
tty=0
[ -t 1 ] && tty=1

while :; do
  all_ok=1
  summary=""
  for svc in "${services[@]}"; do
    status="$(health "$svc")"
    [ "$status" = "healthy" ] || [ "$status" = "no-healthcheck" ] || all_ok=0
    summary+=" ${svc}=${status}"
  done
  elapsed=$(( $(date +%s) - start ))

  if [ "$all_ok" -eq 1 ]; then
    [ "$tty" -eq 1 ] && printf '\r\033[K'
    printf '\xe2\x9c\x94 services ready in %ss:%s\n' "$elapsed" "$summary"
    exit 0
  fi

  if [ "$elapsed" -ge "$TIMEOUT" ]; then
    [ "$tty" -eq 1 ] && printf '\r\033[K'
    printf '\xe2\x9c\x96 timed out after %ss waiting for services:%s\n' "$elapsed" "$summary"
    $COMPOSE ps "${services[@]}" || true
    exit 1
  fi

  frame="${spin:$((i % 4)):1}"
  i=$((i + 1))
  if [ "$tty" -eq 1 ]; then
    printf '\r\033[K%s waiting for services…%s (%ss)' "$frame" "$summary" "$elapsed"
  else
    printf 'waiting for services…%s (%ss)\n' "$summary" "$elapsed"
  fi
  sleep 1
done
