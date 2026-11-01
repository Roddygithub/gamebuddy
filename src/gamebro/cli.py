"""Command line: run the widget, or talk to the running one."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from gamebro import __version__
from gamebro.config import load_config, save_config
from gamebro.ipc import is_running, send_command
from gamebro.paths import config_file, db_file, socket_path

HYPR_RULES_LEGACY = """# GameBro — floating, pinned overlay (Hyprland < 0.53)
windowrulev2 = float, class:^(gamebro)$
windowrulev2 = pin, class:^(gamebro)$
windowrulev2 = size {w} {h}, class:^(gamebro)$
windowrulev2 = move 100%-{wplus} 60, class:^(gamebro)$
windowrulev2 = noborder, class:^(gamebro)$
windowrulev2 = noshadow, class:^(gamebro)$
windowrulev2 = noinitialfocus, class:^(gamebro)$
"""
HYPR_RULES_053 = """# GameBro — floating, pinned overlay (Hyprland 0.53 / 0.54)
windowrule = match:class ^(gamebro)$, float on
windowrule = match:class ^(gamebro)$, pin on
windowrule = match:class ^(gamebro)$, size {w} {h}
windowrule = match:class ^(gamebro)$, move 100%-{wplus} 60
windowrule = match:class ^(gamebro)$, border_size 0
windowrule = match:class ^(gamebro)$, no_shadow on
windowrule = match:class ^(gamebro)$, no_initial_focus on
"""
HYPR_RULES_LUA = """-- GameBro — floating, pinned overlay (Hyprland >= 0.55, Lua config)
hl.window_rule({{ match = {{ class = "^(gamebro)$" }}, float = true, pin = true,
  size = "{w} {h}", move = "100%-{wplus} 60", border_size = 0, no_shadow = true, no_initial_focus = true }})
"""
HYPR_BINDS = """# GameBro — push-to-talk (hold) and widget toggle
bind = {ptt}, exec, gamebro ptt start
bindr = {ptt}, exec, gamebro ptt stop
bind = {toggle}, exec, gamebro toggle
"""


def hyprland_version() -> tuple[int, int] | None:
    if not shutil.which("hyprctl"):
        return None
    try:
        out = subprocess.run(["hyprctl", "version"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"v?(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else None


def hyprland_config(syntax: str = "auto") -> str:
    cfg = load_config()
    w, h = cfg.ui.width, cfg.ui.height
    if syntax == "auto":
        v = hyprland_version()
        syntax = "legacy" if v is None or v < (0, 53) else ("v053" if v < (0, 55) else "lua")
    rules = {"legacy": HYPR_RULES_LEGACY, "v053": HYPR_RULES_053, "lua": HYPR_RULES_LUA}[syntax]
    text = rules.format(w=w, h=h, wplus=w + 20)
    binds = HYPR_BINDS.format(ptt=cfg.hotkeys.push_to_talk, toggle=cfg.hotkeys.toggle_widget)
    if syntax == "lua":
        binds = "-- binds (translate to hl.bind if your binds live in Lua):\n" + "".join(
            "-- " + line + "\n" for line in binds.strip().splitlines()
        )
    return text + "\n" + binds


def doctor() -> int:
    cfg = load_config()
    rows: list[tuple[str, bool, str]] = []
    sysname = platform.system()
    rows.append(("platform", sysname == "Linux", sysname))
    session = (
        "hyprland"
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        else os.environ.get("XDG_SESSION_TYPE", "?")
    )
    rows.append(("session", True, session))
    for tool, why in (
        ("hyprctl", "window list on Hyprland"),
        ("grim", "Wayland screenshots"),
        ("swaymsg", "window list on sway"),
        ("wmctrl", "window list on X11"),
        ("import", "X11 screenshots (ImageMagick)"),
        ("pw-play", "audio playback fallback"),
        ("espeak-ng", "offline TTS"),
        ("piper", "neural offline TTS"),
    ):
        rows.append((tool, shutil.which(tool) is not None, why))
    try:
        import sounddevice as sd

        devs = [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]
        rows.append(("microphone", bool(devs), ", ".join(devs[:3]) or "no input device"))
    except Exception as exc:  # noqa: BLE001
        rows.append(("microphone", False, f"sounddevice/portaudio: {exc}"))
    key = cfg.resolve_api_key()
    if cfg.llm.provider == "codex":
        from gamebro.llm.codex_provider import codex_logged_in

        has_codex = shutil.which(cfg.llm.codex_binary) is not None
        rows.append(("codex cli", has_codex, "found" if has_codex else "npm install -g @openai/codex"))
        logged = codex_logged_in()
        rows.append(("codex login", logged, "ChatGPT account linked" if logged else "run `codex login`"))
    else:
        rows.append(
            (
                f"llm key ({cfg.llm.provider})",
                bool(key) or cfg.llm.provider == "ollama",
                "set" if key else "missing",
            )
        )
    if cfg.speech.stt == "openai" or cfg.speech.tts == "openai":
        rows.append(
            (
                "openai key (voice)",
                bool(cfg.openai_key()),
                "set" if cfg.openai_key() else "missing (use piper/espeak + faster_whisper)",
            )
        )
    else:
        try:
            import faster_whisper  # noqa: F401

            rows.append(("faster-whisper", True, "offline speech-to-text ready"))
        except ImportError:
            rows.append(
                ("faster-whisper", cfg.speech.stt != "faster_whisper", "pip install 'gamebro[local]'")
            )
    rows.append(("config", config_file().is_file(), str(config_file())))
    rows.append(("database", db_file().is_file(), str(db_file())))
    rows.append(("widget running", is_running(), str(socket_path())))
    v = hyprland_version()
    if v:
        rows.append(
            ("hyprland", True, f"{v[0]}.{v[1]} → `gamebro hyprland-config` picks the right rule syntax")
        )
    width = max(len(r[0]) for r in rows)
    bad = 0
    for name, ok, info in rows:
        bad += 0 if ok else 1
        print(f"{'✓' if ok else '✗'} {name.ljust(width)}  {info}")
    return 0 if bad == 0 else 1


def _send(req: dict) -> int:
    if not is_running():
        print("gamebro: widget is not running (start it with `gamebro`)", file=sys.stderr)
        return 3
    resp = send_command(req)
    if req.get("cmd") in ("status", "windows"):
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    elif not resp.get("ok"):
        print(f"gamebro: {resp.get('error', 'error')}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="gamebro", description="GameBro — voice-first AI gaming companion for Linux."
    )
    p.add_argument("--version", action="version", version=f"gamebro {__version__}")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("run", help="start the widget (default)")
    ptt = sub.add_parser("ptt", help="push-to-talk control")
    ptt.add_argument("action", choices=["start", "stop", "toggle"], nargs="?", default="toggle")
    ask = sub.add_parser("ask", help="send a text question to the running widget")
    ask.add_argument("text", nargs="+")
    sub.add_parser("toggle", help="show/hide the widget")
    sub.add_parser("show")
    sub.add_parser("hide")
    sub.add_parser("status", help="print the widget state as JSON")
    sub.add_parser("windows", help="list capturable windows")
    sel = sub.add_parser("select-window", help="select the game window by id (or open the picker)")
    sel.add_argument("id", nargs="?", default="")
    lst = sub.add_parser("listen", help="hands-free listening")
    lst.add_argument("action", choices=["on", "off", "toggle"], nargs="?", default="toggle")
    coach = sub.add_parser("coach", help="coach mode")
    coach.add_argument("action", choices=["on", "off", "toggle"], nargs="?", default="toggle")
    sub.add_parser("unpin")
    sub.add_parser("settings")
    sub.add_parser("quit")
    cap = sub.add_parser("capture", help="capture a window to a file (debug)")
    cap.add_argument("--id", default="", help="window id (default: first non-gamebro window)")
    cap.add_argument("--out", default="gamebro-capture.jpg")
    sub.add_parser("doctor", help="check tools, devices and keys")
    hc = sub.add_parser("hyprland-config", help="print Hyprland rules + binds")
    hc.add_argument("--syntax", choices=["auto", "legacy", "v053", "lua"], default="auto")
    cfgp = sub.add_parser("config", help="config file helpers")
    cfgp.add_argument("action", choices=["path", "show", "init", "edit"], nargs="?", default="path")
    mem = sub.add_parser("memory", help="long-term memory")
    mem.add_argument("action", choices=["list", "forget"], nargs="?", default="list")
    args = p.parse_args(argv)

    cmd = args.cmd or "run"
    if cmd == "run":
        from gamebro.ui.app import run_app

        return run_app()
    if cmd == "ptt":
        return _send({"cmd": "ptt", "action": args.action})
    if cmd == "ask":
        return _send({"cmd": "ask", "text": " ".join(args.text)})
    if cmd in ("toggle", "show", "hide", "status", "unpin", "settings", "quit"):
        return _send({"cmd": cmd})
    if cmd == "windows":
        if is_running():
            return _send({"cmd": "windows"})
        from gamebro.capture import get_backend

        for w in get_backend(load_config().capture.backend).list_windows():
            print(f"{w.id}\t{w.rect.w}x{w.rect.h}\t{w.label}")
        return 0
    if cmd == "select-window":
        return _send({"cmd": "select_window", "id": args.id} if args.id else {"cmd": "pick_window"})
    if cmd == "listen":
        return _send({"cmd": "listen", "action": args.action})
    if cmd == "coach":
        return _send({"cmd": "coach", "action": args.action})
    if cmd == "capture":
        from gamebro.capture import get_backend, to_jpeg

        cfg = load_config()
        backend = get_backend(cfg.capture.backend)
        windows = [w for w in backend.list_windows() if w.app_id.lower() != "gamebro"]
        target = (
            next((w for w in windows if w.id == args.id), None)
            if args.id
            else (windows[0] if windows else None)
        )
        if target is None:
            print("gamebro: no window to capture", file=sys.stderr)
            return 1
        Path(args.out).write_bytes(
            to_jpeg(backend.capture(target), cfg.capture.max_width, cfg.capture.jpeg_quality)
        )
        print(f"captured '{target.title}' → {args.out}")
        return 0
    if cmd == "doctor":
        return doctor()
    if cmd == "hyprland-config":
        print(hyprland_config(args.syntax))
        return 0
    if cmd == "config":
        path = config_file()
        if args.action == "path":
            print(path)
        elif args.action == "init":
            if path.exists():
                print(f"exists: {path}")
            else:
                print(f"written: {save_config(load_config())}")
        elif args.action == "show":
            print(path.read_text() if path.exists() else "(no config yet — defaults in use)")
        elif args.action == "edit":
            if not path.exists():
                save_config(load_config())
            editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
            return subprocess.call([editor, str(path)])
        return 0
    if cmd == "memory":
        from gamebro.memory import Store

        store = Store()
        if args.action == "forget":
            store.forget_all()
            print("memory cleared")
        else:
            for note in store.memories(limit=200):
                print(f"- {note}")
        return 0
    p.print_help()
    return 0
