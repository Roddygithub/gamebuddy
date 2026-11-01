# Changelog

## Unreleased

- New STT engine `voxtype`: reuses Omarchy's dictation tool (`voxtype transcribe`), its model and GPU build. Picked automatically at onboarding when installed; `gamebro doctor` reports it.

## 0.1.1 — 2026-11-01

- `codex` provider: run on a ChatGPT Plus/Pro subscription through the OpenAI Codex CLI (no API key); actions envelope for pin/memory/search; friendly errors; `gamebro doctor` checks the CLI and login.
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
