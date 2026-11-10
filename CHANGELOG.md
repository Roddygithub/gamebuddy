# Changelog

## 0.6.0 — 2026-11-10

- **Buddy has a face that says "talk to me"**: a rounded blob wearing a headset, with pill eyes that
  blink and a mic that emits waves while you speak. Every colour comes from the active theme — body
  on the accent, headset on the secondary colour, eyes on the background — so the mascot changes
  with `omarchy theme set`, and the bar icon is redrawn to match in monochrome.
- **Bounded rendering**: model markdown is capped per answer, its links restricted to the web, the
  transcript keeps a bounded number of bubbles, and typed text and window titles are rendered as
  plain text instead of rich text.
- **Bounded helpers**: the bar's control script gives every engine call an absolute deadline and a
  capped answer, repeated bar clicks can no longer start the widget twice, and hands-free audio is
  admitted one utterance at a time instead of queueing threads.
- **Hash-pinned dependencies**: `requirements.lock` pins the production set with SHA-256 hashes for
  the supported target, and `install.sh` installs it with `--require-hashes`.
- **Bounded paste**: text fields truncate a paste instead of ingesting the whole clipboard.

## 0.5.0 — 2026-11-10

- **The overlay follows the Omarchy theme**: Buddy now reads the active theme's `colors.toml`
  (background, foreground, `accent`, and the ANSI red/green/grey slots) instead of the built-in
  palette, and repaints itself when `omarchy theme set` swaps themes — no restart. The unused
  `ui.theme` option is gone: following the desktop is the only behaviour.
- **All 50 Omarchy languages**: every language `omarchy language list` offers has a full UI
  translation, the language picker lists them by native name, `~/.config/omarchy/language` is
  honoured before the session locale, and Arabic, Hebrew, Persian and Urdu render right to left.

## 0.4.2 — 2026-11-10

- **`gamebuddy ask "…"` prints the answer**: the command waits for the reply on the same IPC
  connection and exits non-zero with the reason when the engine fails, so it composes in scripts
  and keybinds. `--no-wait` keeps the old fire-and-forget behaviour, and the IPC protocol gained
  the matching `{"cmd":"ask","wait":true}` request.
- **Engine errors follow the UI language**: missing Superwhisper, Codex login, voxtype and API-key
  messages are translated in all seven UI languages instead of always appearing in English.
- Refresh the marketplace preview and README screenshots from the current panel.

## 0.4.1 — 2026-11-10

- **The selected game window survives a restart**: GameBuddy remembers the window you chose and
  re-selects it on the next start when a window with the same application and title is open, or
  when that application has a single window. Ambiguous matches are left unselected rather than
  guessing, so a browser or a terminal is never captured by mistake.
- **Coach advice is confirmed before it is spoken**: a passing observation is now only a
  candidate, delivered once the next capture shows the same screen. A HUD flash or a transient
  tooltip no longer produces advice, at the cost of one interval of latency and no extra model
  call. `coach_log` records `pre_gate:await_stability` and `pre_gate:delivered`.

## 0.4.0 — 2026-11-10

- **Superwhisper as a speech-to-text engine**: choose `superwhisper` (or `stt = "superwhisper"`)
  and GameBuddy submits its own recording, then reads that session's transcript without pasting
  into the game. Processing mode, model, language and vocabulary follow Superwhisper's settings;
  microphone capture and shortcuts stay in GameBuddy, and the AI provider and reply voice remain
  configured here.
- **Reliable game-window capture**: the window picker selects the intended window, and Hyprland
  captures only that window through `grim -T` with its `stableId`, even on another workspace.
  A failed window capture no longer falls back to a desktop screenshot.
- **Sharper game vision by default**: `[capture] max_width = 2560` and `jpeg_quality = 90` keep
  small labels, portraits and numbers readable; existing configurations keep their saved values.
  The Dota Underlords instructions distinguish board, bench and shop.
- **Faster spoken replies**: a Piper voice installed in the engine's virtualenv is detected and
  used, the Python Piper voice is preloaded and reused in memory instead of reloading the model
  for each reply, and cached Whisper models are warmed in the background. `gamebuddy status`
  reports the last transcription, response and synthesis durations.
- Refresh the README guides and the current panel/compact-head/orb screenshots.
- Complete the Omarchy Quattro bar plugin with Buddy's themed head, explicit engine startup, AI settings and game-window controls.
- Use Buddy's head in the desktop application launcher as well as the tray.
- Add marketplace preview, dependency/setup/removal documentation and a submission draft.
- Back up compositor files changed by installation and remove owned includes during uninstall.
- Reuse existing virtualenvs during updates and constrain PyAV for local transcription compatibility.
- Store conversation history in a private data directory and protect existing SQLite database/sidecar files.
- Restrict fetched web pages and redirect targets to public IP addresses; pass local eSpeak text through stdin.
- Isolate Codex chats from user configuration and built-in tools; attach only the selected game capture.

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
