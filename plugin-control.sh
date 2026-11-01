#!/bin/sh
# Commands initiated by the Omarchy bar; never install dependencies automatically.
set -eu
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
case "${1:-status}" in
  status)
    if status=$("$engine" status 2>/dev/null); then
      printf '%s\n' "$status"
    else
      printf '%s\n' '{"ok":false,"installed":true}'
    fi
    ;;
  start)
    if "$engine" status >/dev/null 2>&1; then
      exec "$engine" show
    else
      exec "$engine" >/dev/null 2>&1
    fi
    ;;
  show|hide|toggle|ptt|select-window|ai-settings|settings)
    exec "$engine" "$@"
    ;;
  *) printf '%s\n' 'Unsupported GameBuddy plugin action' >&2; exit 2 ;;
esac
