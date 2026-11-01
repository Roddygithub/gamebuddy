#!/usr/bin/env bash
# GameBuddy installer (user-level; root only for the distro package manager).
# Arch/Omarchy (pacman), Debian/Ubuntu (apt), Fedora (dnf), openSUSE (zypper); Hyprland and sway snippets.
#   ./install.sh            install or update
#   ./install.sh uninstall  remove what this script owns
set -euo pipefail

PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/gamebuddy"
VENV="$PREFIX/venv"
BIN="$HOME/.local/bin"
HYPR_DIR="$HOME/.config/hypr"
HYPR_SNIPPET="$HYPR_DIR/gamebuddy.conf"
SWAY_DIR="$HOME/.config/sway"
SWAY_SNIPPET="$SWAY_DIR/gamebuddy.conf"
TRAY_ICON="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/status/gamebuddy-symbolic.svg"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say()  { printf '\033[1;35m[gamebuddy]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[gamebuddy]\033[0m %s\n' "$*" >&2; }

uninstall() {
  say "removing venv, launcher, desktop entry and service"
  systemctl --user disable --now gamebuddy.service gamebuddy-update.timer 2>/dev/null || true
  rm -rf "$VENV" "$BIN/gamebuddy" "$PREFIX/source_dir" "$TRAY_ICON" \
    "$HOME/.config/systemd/user/gamebuddy.service" \
    "$HOME/.config/systemd/user/gamebuddy-update.service" "$HOME/.config/systemd/user/gamebuddy-update.timer" \
    "${XDG_DATA_HOME:-$HOME/.local/share}/applications/gamebuddy.desktop"
  if [ -f "$HYPR_SNIPPET" ]; then
    rm -f "$HYPR_SNIPPET"
    warn "remove the 'source = $HYPR_SNIPPET' line from your hyprland.conf"
  fi
  if [ -f "$SWAY_SNIPPET" ]; then
    rm -f "$SWAY_SNIPPET"
    warn "remove the 'include $SWAY_SNIPPET' line from your sway config"
  fi
  say "kept your config (~/.config/gamebuddy) and database (~/.local/share/gamebuddy/gamebuddy.db)"
  exit 0
}
[ "${1:-}" = "uninstall" ] && uninstall

# ---- system packages -------------------------------------------------------
install_missing() {  # $1 = "check cmd" template with %s, $2 = install cmd, rest = packages
  local check="$1" inst="$2"; shift 2
  local missing=()
  for p in "$@"; do eval "${check//%s/$p}" >/dev/null 2>&1 || missing+=("$p"); done
  if [ ${#missing[@]} -gt 0 ]; then
    say "installing system packages: ${missing[*]} (sudo)"
    # shellcheck disable=SC2086
    sudo $inst "${missing[@]}"
  fi
}
if command -v pacman >/dev/null; then
  install_missing 'pacman -Qi %s' 'pacman -S --needed --noconfirm' python python-pip grim portaudio espeak-ng wl-clipboard
elif command -v apt-get >/dev/null; then
  install_missing 'dpkg -s %s' 'apt-get install -y' python3 python3-venv python3-pip grim libportaudio2 espeak-ng wl-clipboard
elif command -v dnf >/dev/null; then
  install_missing 'rpm -q %s' 'dnf install -y' python3 python3-pip grim portaudio espeak-ng wl-clipboard
elif command -v zypper >/dev/null; then
  install_missing 'rpm -q %s' 'zypper install -y' python3 python3-pip grim portaudio espeak-ng wl-clipboard
else
  warn "unknown package manager: install python>=3.11, grim, portaudio and espeak-ng yourself"
fi
PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0)"
case "$PYV" in 3.1[1-9]|3.[2-9]*) ;; *) warn "python3 is $PYV; GameBuddy needs >= 3.11 (use pyenv/uv: uv python install 3.12)";; esac
case "${XDG_CURRENT_DESKTOP:-}" in
  *GNOME*|*KDE*) say "GNOME/KDE Wayland: game vision uses the whole screen via spectacle / gnome-screenshot / the xdg portal";;
esac

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
install -Dm644 "$SRC_DIR/src/gamebuddy/assets/gamebuddy-symbolic.svg" "$TRAY_ICON"
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

# ---- sway rule + binds -----------------------------------------------------
if [ -n "${SWAYSOCK:-}" ] || [ -f "$SWAY_DIR/config" ]; then
  mkdir -p "$SWAY_DIR"
  "$VENV/bin/gamebuddy" sway-config > "$SWAY_SNIPPET"
  if [ -f "$SWAY_DIR/config" ] && ! grep -q "gamebuddy.conf" "$SWAY_DIR/config"; then
    printf '\n# GameBuddy overlay rule and keybinds\ninclude %s\n' "$SWAY_SNIPPET" >> "$SWAY_DIR/config"
    say "added 'include $SWAY_SNIPPET' to your sway config"
  fi
  command -v swaymsg >/dev/null && swaymsg reload >/dev/null 2>&1 || true
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
