# Architecture

GameBuddy is one Python process (PySide6) plus small system tools. No daemon, no server.

```
src/gamebuddy/
├── cli.py            command line; talks to the running widget over IPC
├── config.py         TOML config (dataclasses, defaults, 0600 when a key is stored)
├── i18n.py           all 50 Omarchy languages, from ~/.config/omarchy/language else the locale
├── ipc.py            Unix socket, newline JSON; single-instance lock; event broadcast
├── kin.py            orchestrator: system prompt, tool loop, history, pins, memory
├── prompts.py        Ask-mode and Coach-mode prompts
├── memory.py         SQLite: conversations, messages, memories, pin, coach_log
├── llm/              provider-neutral Message/ToolSpec; Anthropic + OpenAI-compatible backends
├── tools/            web_search, fetch_page, pin_content, unpin_content, remember, recall
├── capture/          hyprland (hyprctl+grim), sway (swaymsg+grim), wlroots (grim), x11, macos (dev)
├── audio/            Recorder (push-to-talk), HandsFreeListener (energy VAD), player
├── speech/           STT (openai, faster_whisper, whispercpp), TTS (openai, piper, espeak)
├── coach/            observer (dhash), gate (grounding checks), pipeline (loop + logging)
└── ui/               widget, picker, settings, onboarding, theme, bridge (Qt signals), app wiring
```

## Threads

- GUI thread: Qt widgets only.
- `QThreadPool` workers: capture → LLM call → tool execution → TTS. Results come back through
  `ui/bridge.py` signals (queued connections).
- `gamebuddy-ipc` thread: accepts socket connections; read-only requests (`ping`, `status`,
  `windows`) are answered in place, everything else is emitted as a `command` signal and
  executed on the GUI thread.
- Audio callbacks run on the PortAudio thread and only append to buffers / emit levels.
- `gamebuddy-coach` thread: the observation loop.

## Conversation history

History is stored provider-neutrally (`Message.to_record`). Assistant turns also keep the
provider's raw content blocks (`raw`), so Anthropic turns are replayed verbatim (thinking and
`tool_use` blocks intact). Tool results are grouped into one user message for Anthropic and
emitted as `role: tool` for OpenAI-compatible APIs. `recent_messages()` trims a dangling tool
call at the end of the window so a replay never starts with an orphan result.

## Capture

The model should see the game, not the widget. On Hyprland the widget's own client rectangle
is read from `hyprctl -j clients` (class `gamebuddy`) and blacked out before encoding; elsewhere
the Qt frame geometry is used. Capture is a region screenshot (`grim -g`), so an overlapping
window would show through — the planned fix is a `hyprland-toplevel-export` backend, the same
mechanism Quickshell's `ScreencopyView` uses in OmaPiP.

## Why Qt and not a Quickshell/QML panel

Quickshell would give a true layer-shell overlay and shares the OmaPiP toolchain, but the
audio, model and tool pipeline is Python. The split keeps the widget usable on any Wayland
compositor or X11; the IPC event stream (`{"cmd": "subscribe"}`) exists precisely so a QML
panel can be written later without touching the core.
