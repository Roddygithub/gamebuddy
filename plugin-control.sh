#!/bin/sh
# Commands initiated by the Omarchy bar; never install dependencies automatically.
#
# The bar polls this script, so every engine call gets an absolute deadline and
# a capped answer: a wedged widget or a child that refuses to die can hold the
# bar for seconds, never forever.
set -eu

deadline=6 # seconds for a status/control round trip
start_deadline=15 # a cold start has to build its venv the first time
max_output=2048 # bytes of engine output the bar will ever parse

engine=$(command -v gamebuddy 2>/dev/null || true)
if [ -z "$engine" ] && [ -x "$HOME/.local/bin/gamebuddy" ]; then
  engine="$HOME/.local/bin/gamebuddy"
fi
if [ -z "$engine" ]; then
  if [ "${1:-status}" = status ]; then
    printf '%s\n' '{"ok":false,"installed":false}'
    exit 0
  fi
  if command -v notify-send >/dev/null 2>&1; then
    notify-send GameBuddy 'Install the GameBuddy engine first; see the plugin README.'
  fi
  exit 127
fi

# timeout(1) kills the call's leader and its descendants after the grace
# period, so a half-dead helper cannot outlive it. Without coreutils we still
# work, just without the deadline.
if command -v timeout >/dev/null 2>&1; then
  bounded() {
    limit=$1
    shift
    timeout --kill-after=2 "$limit" "$engine" "$@" 2>/dev/null || true
  }
else
  bounded() {
    shift
    "$engine" "$@" 2>/dev/null || true
  }
fi

case "${1:-status}" in
  status)
    status=$(bounded "$deadline" status)
    if [ -n "$status" ]; then
      # One line, capped: the bar parses JSON, not an essay.
      printf '%s\n' "$status" | head -c "$max_output" | head -n 1
    else
      printf '%s\n' '{"ok":false,"installed":true}'
    fi
    ;;
  start)
    if bounded "$deadline" status | grep -q '"ok":true'; then
      bounded "$deadline" show >/dev/null
    else
      timeout --kill-after=2 "$start_deadline" "$engine" >/dev/null 2>&1 || true
    fi
    ;;
  show|hide|toggle|ptt|select-window|ai-settings|settings)
    bounded "$deadline" "$@"
    ;;
  *)
    printf '%s\n' 'Unsupported GameBuddy plugin action' >&2
    exit 2
    ;;
esac
