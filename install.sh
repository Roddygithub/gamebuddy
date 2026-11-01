#!/usr/bin/env bash
# GameBuddy installer for Arch Linux / Omarchy (user-level, no root except pacman).
#   ./install.sh            install or update
#   ./install.sh uninstall  remove what this script owns
set -euo pipefail

PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/gamebuddy"
VENV="$PREFIX/venv"
BIN="$HOME/.local/bin"
HYPR_DIR="$HOME/.config/hypr"
HYPR_SNIPPET="$HYPR_DIR/gamebuddy.conf"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say()  { printf '\033[1;35m[gamebuddy]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[gamebuddy]\033[0m %s\n' "$*" >&2; }

uninstall() {
  say "removing venv, launcher, desktop entry and service"
  systemctl --user disable --now gamebuddy.service gamebuddy-update.timer 2>/dev/null || true
  rm -rf "$VENV" "$BIN/gamebuddy" "$PREFIX/source_dir" \
    "$HOME/.config/systemd/user/gamebuddy.service" \
    "$HOME/.config/systemd/user/gamebuddy-update.service" "$HOME/.config/systemd/user/gamebuddy-update.timer" \
    "${XDG_DATA_HOME:-$HOME/.local/share}/applications/gamebuddy.desktop"
  if [ -f "$HYPR_SNIPPET" ]; then
    rm -f "$HYPR_SNIPPET"
    warn "remove the 'source = $HYPR_SNIPPET' line from your hyprland.conf"
  fi
  say "kept your config (~/.config/gamebuddy) and database (~/.local/share/gamebuddy/gamebuddy.db)"
  exit 0
}
[ "${1:-}" = "uninstall" ] && uninstall

# ---- system packages -------------------------------------------------------
if command -v pacman >/dev/null; then
  PKGS=(python python-pip grim portaudio espeak-ng wl-clipboard)
  MISSING=()
  for p in "${PKGS[@]}"; do pacman -Qi "$p" >/dev/null 2>&1 || MISSING+=("$p"); done
  if [ ${#MISSING[@]} -gt 0 ]; then
    say "installing system packages: ${MISSING[*]} (sudo)"
    sudo pacman -S --needed --noconfirm "${MISSING[@]}"
  fi
else
  warn "not an Arch system: install python>=3.11, grim, portaudio and espeak-ng with your package manager"
fi

# ---- legacy GameBro (<= 0.1.1) ---------------------------------------------
LEGACY_PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/gamebro"
if [ -d "$LEGACY_PREFIX" ] || [ -L "$BIN/gamebro" ]; then
  say "removing the old GameBro install (config and database are migrated on first start)"
  systemctl --user disable --now gamebro.service 2>/dev/null || true
  rm -f "$BIN/gamebro" "$HOME/.config/systemd/user/gamebro.service" \
    "${XDG_DATA_HOME:-$HOME/.local/share}/applications/gamebro.desktop" "$HYPR_DIR/gamebro.conf"
  rm -rf "$LEGACY_PREFIX/venv"
  if [ -f "$HYPR_DIR/hyprland.conf" ] && grep -q "gamebro.conf" "$HYPR_DIR/hyprland.conf"; then
    sed -i '/gamebro.conf/d; /# GameBro overlay rules and keybinds/d' "$HYPR_DIR/hyprland.conf"
  fi
fi

# ---- virtualenv ------------------------------------------------------------
mkdir -p "$PREFIX" "$BIN"
if command -v uv >/dev/null; then
  say "creating venv with uv"
  uv venv --quiet "$VENV"
  uv pip install --quiet --python "$VENV/bin/python" "$SRC_DIR[local]"
else
  say "creating venv with python -m venv"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet "$SRC_DIR[local]"
fi
ln -sf "$VENV/bin/gamebuddy" "$BIN/gamebuddy"
case ":$PATH:" in *":$BIN:"*) ;; *) warn "add $BIN to your PATH";; esac

# ---- desktop entry + systemd user service ----------------------------------
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPS" "$HOME/.config/systemd/user"
sed "s|@BIN@|$VENV/bin/gamebuddy|g" "$SRC_DIR/packaging/gamebuddy.desktop" > "$APPS/gamebuddy.desktop"
sed "s|@BIN@|$VENV/bin/gamebuddy|g" "$SRC_DIR/packaging/gamebuddy.service" > "$HOME/.config/systemd/user/gamebuddy.service"
sed "s|@BIN@|$VENV/bin/gamebuddy|g" "$SRC_DIR/packaging/gamebuddy-update.service" > "$HOME/.config/systemd/user/gamebuddy-update.service"
cp "$SRC_DIR/packaging/gamebuddy-update.timer" "$HOME/.config/systemd/user/gamebuddy-update.timer"
printf '%s\n' "$SRC_DIR" > "$PREFIX/source_dir"   # `gamebuddy update` pulls new tags here
systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable --now gamebuddy-update.timer 2>/dev/null || true

# ---- Hyprland rules + binds ------------------------------------------------
if [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || [ -d "$HYPR_DIR" ]; then
  mkdir -p "$HYPR_DIR"
  "$VENV/bin/gamebuddy" hyprland-config > "$HYPR_SNIPPET"
  MAIN="$HYPR_DIR/hyprland.conf"
  if [ -f "$MAIN" ] && ! grep -q "gamebuddy.conf" "$MAIN"; then
    printf '\n# GameBuddy overlay rules and keybinds\nsource = %s\n' "$HYPR_SNIPPET" >> "$MAIN"
    say "added 'source = $HYPR_SNIPPET' to hyprland.conf"
  fi
  command -v hyprctl >/dev/null && hyprctl reload >/dev/null 2>&1 || true
fi

if ! command -v codex >/dev/null; then
  warn "Codex CLI not found. To use a ChatGPT Plus/Pro subscription (no API key):"
  warn "  npm install -g @openai/codex && codex login"
fi

say "installed. Next:"
echo "  codex login                  (ChatGPT Plus/Pro, no API key) — or export ANTHROPIC_API_KEY / OPENAI_API_KEY"
echo "  gamebuddy doctor"
echo "  gamebuddy                      # first run opens the onboarding wizard"
echo "  systemctl --user enable --now gamebuddy   # optional autostart"
echo "  gamebuddy update                          # later: pull the latest release (daily check is on)"
