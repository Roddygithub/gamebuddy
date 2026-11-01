# Changelog

## 0.3.1

- **GNOME and KDE Wayland get game vision**: new `portal` capture backend (whole screen) through `spectacle`, `gnome-screenshot` or the `org.freedesktop.portal.Screenshot` D-Bus portal (jeepney). Picked automatically from `XDG_CURRENT_DESKTOP`; `gamebuddy doctor` shows which backend is in use.
- **sway**: `gamebuddy sway-config` prints the `for_window` rule and push-to-talk/toggle `bindsym`s; `install.sh` writes and includes `~/.config/sway/gamebuddy.conf`.
- **Installer** handles apt, dnf and zypper besides pacman, and warns when `python3` is older than 3.11.
- **Ollama**: models without tool support no longer break a question (GameBuddy retries without tools); the suggested local model is now `qwen3-vl` (vision + tools).

## 0.3.0

- **Buddy has a face.** Vector avatar (no image assets) with four animated states: idle (blinks), listening (ring pulses with the mic level), thinking (orbiting dots), speaking (mouth moves). Colors follow the theme / Omarchy palette.
- **Orb mode is the new in-game default**: only the avatar and his last words (a caption that fades after a few seconds) stay on screen; clicks outside the orb reach the game. Click the avatar to open the full panel; pinned content opens it automatically; `ui.mode = "panel"` restores the old behaviour. `gamebuddy hyprland-config` sizes the window for the configured start mode.

## 0.2.1

- Self-update: `gamebuddy update` fetches the latest GitHub release tag into the install source and re-runs `install.sh`, then restarts the widget. A daily systemd user timer (`gamebuddy-update.timer`) checks for releases; `general.auto_update` = `notify` (default: bubble + tray action "Update to X") | `auto` (the timer installs it) | `off`.
- GitHub release workflow on `v*` tags (notes taken from this changelog).

## 0.2.0

- **Renamed GameBro → GameBuddy.** Package, CLI (`gamebuddy`), socket, config/data dirs, Hyprland class, systemd unit and Omarchy plugin id all follow. Existing `~/.config/gamebro` and `~/.local/share/gamebro` are moved automatically on first start; re-run `./install.sh` (it replaces the old `gamebro` symlink, desktop entry, service and Hyprland snippet).
- New STT engine `voxtype`: reuses Omarchy's dictation tool (`voxtype transcribe`), its model and GPU build. Picked automatically at onboarding when installed; `gamebuddy doctor` reports it.

## 0.1.1 — 2026-11-01

- `codex` provider: run on a ChatGPT Plus/Pro subscription through the OpenAI Codex CLI (no API key); actions envelope for pin/memory/search; friendly errors; `gamebuddy doctor` checks the CLI and login.
- Installer installs the offline speech extra (faster-whisper) by default.

## 0.1.0 — 2026-11-01

First public version.

- Qt widget: status, transcript, pinned panel, push-to-talk / hands-free mic button, compact mode.
- Providers: Anthropic (streaming, tools, vision), OpenAI-compatible (OpenAI, Ollama, LM Studio…).
- Tools: web search, page fetch, pin/unpin, remember/recall.
- Capture: Hyprland, sway, generic wlroots, X11, macOS (dev); overlay masking.
- Voice: OpenAI / faster-whisper / whisper.cpp STT; OpenAI / piper / espeak-ng TTS.
- Coach mode with structured-state gate and audit log.
- IPC socket + CLI; Hyprland config generator for three rule syntaxes; Omarchy bar widget;
  installer, desktop entry, systemd user service, PKGBUILD.
