# GameBro

<p align="center"><strong>Voice-first AI gaming companion for Linux</strong><br>
Stay in your game, talk to Bro. A GameKin-like widget for Wayland, Hyprland and Omarchy.</p>

<p align="center">
  <a href="https://github.com/Roddygithub/gamebro/actions/workflows/ci.yml"><img src="https://github.com/Roddygithub/gamebro/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Roddygithub/gamebro" alt="MIT"></a>
  <a href="README.fr.md">🇫🇷 Version française</a>
</p>

<p align="center"><img src="docs/assets/widget-fr.png" alt="GameBro widget" width="420"></p>

GameBro is an AI companion named **Bro** that lives in one small widget next to your game.
Hold a key and talk; Bro can see the game window you selected, search the web,
answer in your language, keep builds and checklists pinned on screen, and remember
useful details between sessions. It **advises only**: it never injects input,
reads game memory, or plays for you.

Everything runs locally except the AI calls you configure (bring your own key, or a
local model through Ollama).

## Features

- **Voice-first** — hold `Alt+V` (configurable) to talk, or turn on hands-free listening. Typing works too.
- **Sees your game** — with your selection, Bro captures the chosen window (Hyprland, sway, generic wlroots, X11) and masks its own widget out of the frame.
- **Search and knowledge** — web search + page reading for patch notes, meta, builds; model knowledge for strategy.
- **Continuous conversation** — the thread persists across restarts; long-term notes live in a local SQLite database.
- **Pinned content** — builds, checklists, tables, links or video URLs stay visible until you replace or remove them.
- **Spoken replies** — OpenAI TTS, [piper](https://github.com/rhasspy/piper) or espeak-ng; speech-to-text through OpenAI, faster-whisper (offline) or whisper.cpp.
- **Coach mode (opt-in, experimental)** — periodic observation with a cautious grounding gate; silent unless a long-lived decision window is clearly visible. See [docs/COACH-MODE.md](docs/COACH-MODE.md).
- **Multilingual** — UI in French, English, German, Spanish, Italian, Brazilian and European Portuguese; Bro answers in whatever language you speak.
- **Providers** — Anthropic Claude, OpenAI, Ollama, or any OpenAI-compatible endpoint (LM Studio, OpenRouter, Mistral…).
- **Scriptable** — a Unix-socket IPC and a CLI (`gamebro ptt start`, `gamebro ask "…"`, `gamebro toggle`), which is how Hyprland keybinds and the Omarchy bar widget drive it.

## Quick start (Arch Linux / Omarchy)

```bash
git clone https://github.com/Roddygithub/gamebro.git
cd gamebro
./install.sh
```

The installer installs system tools with pacman (`grim`, `python`, `portaudio`, `espeak-ng`…),
creates an isolated virtualenv under `~/.local/share/gamebro/venv`, links the `gamebro`
command into `~/.local/bin`, adds the Hyprland rules and keybinds to `~/.config/hypr/`,
and installs a desktop entry plus a `systemd --user` service (not enabled by default).

Then:

```bash
export ANTHROPIC_API_KEY=sk-ant-…     # or OPENAI_API_KEY, or use Ollama
gamebro                               # first run opens the onboarding wizard
```

Optional Omarchy bar widget (an icon that shows/hides Bro):

```bash
omarchy plugin add https://github.com/Roddygithub/gamebro.git --enable
omarchy bar put gamebro --after omarchy.clock
```

### Manual install (any distro)

```bash
pipx install 'git+https://github.com/Roddygithub/gamebro.git'    # or: uv tool install …
gamebro hyprland-config >> ~/.config/hypr/hyprland.conf          # Hyprland users
gamebro doctor                                                    # check tools, mic, keys
gamebro
```

Required system packages: `grim` (Wayland screenshots), `portaudio` (microphone), optionally
`espeak-ng` or `piper` for offline speech, `wmctrl` + ImageMagick on X11.

## How it works

```
                 ┌───────────── GameBro widget (PySide6) ─────────────┐
 Alt+V  ──IPC──▶ │ push-to-talk ─▶ STT ─▶ Bro (LLM + tools) ─▶ TTS   │
 gamebro ask ──▶ │       ▲                   │                        │
                 │  game window capture ─────┘  pin / remember / web  │
                 └────────────────────────────────────────────────────┘
```

- **Capture**: `hyprctl -j clients` + `grim -g` on Hyprland (sway and X11 equivalents). The widget's own rectangle is blacked out before the frame is sent to the model. Capture happens only when you ask something (or when coach mode is on).
- **Ask mode**: your question + an optional screenshot + recent conversation + long-term notes go to the configured model with tools `web_search`, `fetch_page`, `pin_content`, `unpin_content`, `remember`, `recall`.
- **Coach mode**: capture → perceptual-hash change filter → structured-state JSON from a cheap model → hard grounding gate (ownership, open decision window, evidence, no critical unknowns, advice must name a visible option) → one short line in the widget. Everything is logged in the `coach_log` table so false positives can be audited.

More in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Configuration

`~/.config/gamebro/config.toml` (created with `gamebro config init`, edited in the Settings dialog or with `gamebro config edit`):

```toml
[general]
language = "auto"          # fr, en, de, es, it, pt-BR, pt-PT
assistant_name = "Bro"
personality = "coach"      # coach | friendly | concise

[hotkeys]
push_to_talk = "ALT, V"    # Hyprland bind syntax
toggle_widget = "ALT, B"

[llm]
provider = "anthropic"     # anthropic | openai | ollama | openai_compatible
model = "claude-opus-5-5"
effort = "low"             # Anthropic: low keeps answers fast and cheap mid-game
api_key = ""               # or ANTHROPIC_API_KEY / OPENAI_API_KEY in the environment

[speech]
stt = "openai"             # openai | faster_whisper | whispercpp | none
tts = "openai"             # openai | piper | espeak | none
speak_replies = true

[coach]
enabled = false
interval_s = 4.0
model = ""                 # cheap default per provider (claude-haiku-5-5 / gpt-4o-mini)
```

Local, offline setup: `provider = "ollama"`, `model = "llama3.2-vision"`, `stt = "faster_whisper"` (`pip install 'gamebro[local]'`), `tts = "piper"`.

## Hyprland

`gamebro hyprland-config` prints the rules and binds for your Hyprland version
(legacy `windowrulev2`, the 0.53+ `match:` syntax, or Lua for 0.55+). The widget
is a floating, pinned window, so it stays visible across workspaces and above
windowed / borderless-fullscreen games. Exclusive fullscreen is not guaranteed,
as with the original.

```
bind  = ALT, V, exec, gamebro ptt start
bindr = ALT, V, exec, gamebro ptt stop
bind  = ALT, B, exec, gamebro toggle
```

GNOME, KDE and X11 users bind the same commands with their desktop's shortcut settings.

## CLI

| Command | Effect |
|---|---|
| `gamebro` | start the widget (single instance) |
| `gamebro ptt start\|stop\|toggle` | push-to-talk |
| `gamebro ask "which item?"` | type a question from a script |
| `gamebro toggle` / `show` / `hide` | widget visibility |
| `gamebro listen on\|off` | hands-free listening |
| `gamebro coach on\|off` | coach mode |
| `gamebro select-window [id]` | choose the game window (`gamebro windows` lists ids) |
| `gamebro capture --out shot.jpg` | debug a capture |
| `gamebro doctor` | check tools, microphone, keys, Hyprland version |
| `gamebro hyprland-config` | print rules + binds |
| `gamebro memory list\|forget` | inspect or wipe long-term notes |

## Privacy

- Screenshots are taken only when you ask (or when coach mode is on) and are sent only to the provider you configured. Nothing is written to disk except the conversation text and your notes in `~/.local/share/gamebro/gamebro.db`.
- API keys stay in `config.toml` (mode 600) or in your environment.
- No telemetry, no account, no server of ours.

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -e '.[dev]'
pytest
ruff check src tests
```

Tests run headless (`QT_QPA_PLATFORM=offscreen`) with a scripted provider, so they need no API key.
The capture backends and the Qt widget are exercised on Linux CI; audio and real
compositor behaviour need a desktop session.

## Status

0.1.0 — first public version. Known limits:

- Per-window capture uses region screenshots; a window hidden behind another will show what is on top. A `hyprland-toplevel-export` backend (what OmaPiP uses) is a planned improvement.
- Global hotkeys on Wayland go through the compositor (Hyprland binds). An X11 in-process listener is available with `pip install 'gamebro[x11]'` and `hotkeys.x11_listener = true`.
- Coach mode is experimental and conservative by design; expect it to stay silent most of the time.

## License

MIT — see [LICENSE](LICENSE). GameKin is a trademark of its owner; GameBro is an independent project and is not affiliated with it.
