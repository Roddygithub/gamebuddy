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
from importlib.util import find_spec
from pathlib import Path

from gamebuddy import __version__
from gamebuddy.config import load_config, save_config
from gamebuddy.ipc import is_running, send_command
from gamebuddy.paths import config_file, db_file, socket_path

HYPR_RULES_LEGACY = """# GameBuddy — floating, pinned overlay (Hyprland < 0.53)
windowrulev2 = float, class:^(gamebuddy)$, initialTitle:^(GameBuddy)$
windowrulev2 = pin, class:^(gamebuddy)$, initialTitle:^(GameBuddy)$
windowrulev2 = size {w} {h}, class:^(gamebuddy)$, initialTitle:^(GameBuddy)$
windowrulev2 = move 100%-{wplus} 60, class:^(gamebuddy)$, initialTitle:^(GameBuddy)$
windowrulev2 = noborder, class:^(gamebuddy)$, initialTitle:^(GameBuddy)$
windowrulev2 = noshadow, class:^(gamebuddy)$, initialTitle:^(GameBuddy)$
windowrulev2 = noinitialfocus, class:^(gamebuddy)$, initialTitle:^(GameBuddy)$
"""
HYPR_RULES_053 = """# GameBuddy — floating, pinned overlay (Hyprland 0.53 / 0.54)
windowrule = match:class ^(gamebuddy)$, match:initial_title ^(GameBuddy)$, float on
windowrule = match:class ^(gamebuddy)$, match:initial_title ^(GameBuddy)$, pin on
windowrule = match:class ^(gamebuddy)$, match:initial_title ^(GameBuddy)$, size {w} {h}
windowrule = match:class ^(gamebuddy)$, match:initial_title ^(GameBuddy)$, move 100%-{wplus} 60
windowrule = match:class ^(gamebuddy)$, match:initial_title ^(GameBuddy)$, border_size 0
windowrule = match:class ^(gamebuddy)$, match:initial_title ^(GameBuddy)$, no_shadow on
windowrule = match:class ^(gamebuddy)$, match:initial_title ^(GameBuddy)$, no_initial_focus on
"""
HYPR_RULES_LUA = """-- GameBuddy — floating, pinned overlay (Hyprland >= 0.55, Lua config)
hl.window_rule({{ match = {{ class = "^(gamebuddy)$", initial_title = "^(GameBuddy)$" }}, float = true, pin = true,
  size = "{w} {h}", move = "100%-{wplus} 60", border_size = 0, no_shadow = true, no_initial_focus = true }})
"""
SWAY_RULES = """# GameBuddy — floating, sticky overlay (sway)
for_window [app_id="gamebuddy" title="^GameBuddy$"] floating enable, sticky enable, border none, resize set {w} {h}
# GameBuddy — push-to-talk (hold) and widget toggle
bindsym --no-repeat {ptt} exec gamebuddy ptt start
bindsym --release {ptt} exec gamebuddy ptt stop
bindsym {toggle} exec gamebuddy toggle
"""
HYPR_BINDS = """# GameBuddy — push-to-talk (hold) and widget toggle
bind = {ptt}, exec, gamebuddy ptt start
bindr = {ptt}, exec, gamebuddy ptt stop
bind = {toggle}, exec, gamebuddy toggle
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
    if cfg.ui.mode == "orb":
        from gamebuddy.ui.widget import ORB_H, ORB_W

        w, h = ORB_W, ORB_H  # the panel resizes itself when opened (floating windows may do so)
    if syntax == "auto":
        v = hyprland_version()
        syntax = "legacy" if v is None or v < (0, 53) else ("v053" if v < (0, 55) else "lua")
    rules = {"legacy": HYPR_RULES_LEGACY, "v053": HYPR_RULES_053, "lua": HYPR_RULES_LUA}[syntax]
    text = rules.format(w=w, h=h, wplus=w + 20)
    if cfg.ui.compact_orb == "auto":
        # Let Qt choose the size for the screen where the widget actually opens.
        if syntax == "lua":
            text = text.replace(f'size = "{w} {h}", ', "")
        else:
            text = "\n".join(line for line in text.splitlines() if "size " not in line) + "\n"
    from gamebuddy.hotkeys import hypr_bindings

    binds = hypr_bindings(cfg.hotkeys, syntax == "lua")
    return text + "\n" + binds


_SWAY_MODS = {"SUPER": "Mod4", "ALT": "Mod1", "CTRL": "Control", "CONTROL": "Control", "SHIFT": "Shift"}


def sway_key(hypr_bind: str) -> str:
    """'ALT, V' → 'Mod1+v'; 'SUPER SHIFT, B' → 'Mod4+Shift+b'."""
    mods, _, key = hypr_bind.partition(",")
    parts = [_SWAY_MODS.get(m.upper(), m) for m in mods.replace("+", " ").split()]
    return "+".join(parts + [key.strip().lower() or "v"])


def sway_config() -> str:
    cfg = load_config()
    w, h = cfg.ui.width, cfg.ui.height
    if cfg.ui.mode == "orb":
        from gamebuddy.ui.widget import ORB_H, ORB_W

        w, h = ORB_W, ORB_H
    text = SWAY_RULES.format(
        w=w, h=h, ptt=sway_key(cfg.hotkeys.push_to_talk), toggle=sway_key(cfg.hotkeys.toggle_widget)
    )
    if cfg.hotkeys.mode == "toggle":
        text = text.replace("ptt start", "ptt toggle")
        text = "\n".join(line for line in text.splitlines() if "ptt stop" not in line) + "\n"
    if cfg.ui.compact_orb == "auto":
        text = text.replace(f", resize set {w} {h}", "")
    return text


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
    from gamebuddy.capture.base import detect_session

    kind = detect_session() if cfg.capture.backend in ("", "auto") else cfg.capture.backend
    rows.append(
        (
            "capture backend",
            kind not in ("none",),
            {
                "hyprland": "window capture (hyprctl + grim)",
                "sway": "window capture (swaymsg + grim)",
                "wlroots": "whole screen (grim) — no window list on this compositor",
                "portal": "whole screen via spectacle / gnome-screenshot / xdg portal (GNOME, KDE)",
                "x11": "window capture (wmctrl + ImageMagick)",
                "macos": "dev only",
            }.get(kind, kind),
        )
    )
    for tool, why in (
        ("hyprctl", "window list on Hyprland"),
        ("grim", "Wayland screenshots"),
        ("swaymsg", "window list on sway"),
        ("wmctrl", "window list on X11"),
        ("import", "X11 screenshots (ImageMagick)"),
        ("spectacle", "KDE Wayland screenshots"),
        ("gnome-screenshot", "GNOME Wayland screenshots"),
        ("pw-play", "audio playback fallback"),
        ("espeak-ng", "offline TTS"),
        ("piper", "neural offline TTS"),
    ):
        available = shutil.which(tool) is not None
        if tool == "piper":
            available = available or find_spec("piper") is not None
        rows.append((tool, available, why))
    try:
        import sounddevice as sd

        devs = [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]
        rows.append(("microphone", bool(devs), ", ".join(devs[:3]) or "no input device"))
    except Exception as exc:  # noqa: BLE001
        rows.append(("microphone", False, f"sounddevice/portaudio: {exc}"))
    if cfg.speech.stt == "superwhisper":
        rows.append(
            (
                "superwhisper",
                shutil.which("superwhisper") is not None,
                "STT using saved Superwhisper settings",
            )
        )
    key = cfg.resolve_api_key()
    if cfg.llm.provider == "codex":
        from gamebuddy.llm.codex_provider import codex_logged_in

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
    elif cfg.speech.stt == "voxtype":
        from gamebuddy.speech.stt import voxtype_available

        has_vox = voxtype_available(cfg.speech.voxtype_binary)
        rows.append(
            (
                "voxtype",
                has_vox,
                "offline speech-to-text via Omarchy's dictation tool"
                if has_vox
                else "Omarchy: Install > AI > Dictation (or `yay -S voxtype`)",
            )
        )
    else:
        try:
            import faster_whisper  # noqa: F401

            rows.append(("faster-whisper", True, "offline speech-to-text ready"))
        except ImportError:
            rows.append(
                ("faster-whisper", cfg.speech.stt != "faster_whisper", "pip install 'gamebuddy[local]'")
            )
    rows.append(("config", config_file().is_file(), str(config_file())))
    rows.append(("database", db_file().is_file(), str(db_file())))
    rows.append(("widget running", is_running(), str(socket_path())))
    rows.append(
        ("auto-update", True, f"general.auto_update = {cfg.general.auto_update} (`gamebuddy update`)")
    )
    v = hyprland_version()
    if v:
        rows.append(
            ("hyprland", True, f"{v[0]}.{v[1]} → `gamebuddy hyprland-config` picks the right rule syntax")
        )
    width = max(len(r[0]) for r in rows)
    bad = 0
    for name, ok, info in rows:
        bad += 0 if ok else 1
        print(f"{'✓' if ok else '✗'} {name.ljust(width)}  {info}")
    return 0 if bad == 0 else 1


def _send(req: dict) -> int:
    if not is_running():
        print("gamebuddy: widget is not running (start it with `gamebuddy`)", file=sys.stderr)
        return 3
    resp = send_command(req)
    if req.get("cmd") in ("status", "windows"):
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    elif not resp.get("ok"):
        print(f"gamebuddy: {resp.get('error', 'error')}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="gamebuddy", description="GameBuddy — voice-first AI gaming companion for Linux."
    )
    p.add_argument("--version", action="version", version=f"gamebuddy {__version__}")
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
    sub.add_parser("ai-settings", help="open the AI settings tab")
    sub.add_parser("quit")
    cap = sub.add_parser("capture", help="capture a window to a file (debug)")
    cap.add_argument("--id", default="", help="window id (default: first non-gamebuddy window)")
    cap.add_argument("--out", default="gamebuddy-capture.jpg")
    sub.add_parser("doctor", help="check tools, devices and keys")
    upd = sub.add_parser("update", help="update to the latest GitHub release (git + install.sh)")
    upd.add_argument("--check", action="store_true", help="only report whether an update exists")
    upd.add_argument("--if-available", action="store_true", help="do nothing when already up to date")
    upd.add_argument("--quiet", action="store_true")
    upd.add_argument(
        "--respect-policy", action="store_true", help='install only when general.auto_update = "auto"'
    )
    hc = sub.add_parser("hyprland-config", help="print Hyprland rules + binds")
    sub.add_parser("sway-config", help="print sway for_window rule + bindsyms")
    hc.add_argument("--syntax", choices=["auto", "legacy", "v053", "lua"], default="auto")
    cfgp = sub.add_parser("config", help="config file helpers")
    cfgp.add_argument("action", choices=["path", "show", "init", "edit"], nargs="?", default="path")
    mem = sub.add_parser("memory", help="long-term memory")
    mem.add_argument("action", choices=["list", "forget"], nargs="?", default="list")
    args = p.parse_args(argv)

    cmd = args.cmd or "run"
    if cmd == "run":
        from gamebuddy.ui.app import run_app

        return run_app()
    if cmd == "ptt":
        return _send({"cmd": "ptt", "action": args.action})
    if cmd == "ask":
        return _send({"cmd": "ask", "text": " ".join(args.text)})
    if cmd in ("toggle", "show", "hide", "status", "unpin", "settings", "ai-settings", "quit"):
        return _send({"cmd": cmd})
    if cmd == "windows":
        if is_running():
            return _send({"cmd": "windows"})
        from gamebuddy.capture import get_backend

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
        from gamebuddy.capture import get_backend, to_jpeg

        cfg = load_config()
        backend = get_backend(cfg.capture.backend)
        windows = [w for w in backend.list_windows() if w.app_id.lower() != "gamebuddy"]
        target = (
            next((w for w in windows if w.id == args.id), None)
            if args.id
            else (windows[0] if windows else None)
        )
        if target is None:
            print("gamebuddy: no window to capture", file=sys.stderr)
            return 1
        Path(args.out).write_bytes(
            to_jpeg(backend.capture(target), cfg.capture.max_width, cfg.capture.jpeg_quality)
        )
        print(f"captured '{target.title}' → {args.out}")
        return 0
    if cmd == "doctor":
        return doctor()
    if cmd == "update":
        from gamebuddy.update import UpdateError, check_for_update, run_update

        try:
            policy = load_config().general.auto_update
            if args.check or (args.respect_policy and policy != "auto"):
                if args.respect_policy and policy == "off":
                    return 0
                info = check_for_update(force=True)
                if info["available"]:
                    print(f"update available: {info['installed']} → {info['latest']}  ({info['url']})")
                    print("run: gamebuddy update")
                    return 10 if args.check else 0
                if not args.quiet:
                    print(f"gamebuddy {info['installed']} is up to date")
                return 0
            return run_update(only_if_available=args.if_available, quiet=args.quiet)
        except UpdateError as exc:
            print(f"gamebuddy: update failed: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001 — network errors
            print(f"gamebuddy: could not reach GitHub: {exc}", file=sys.stderr)
            return 1
    if cmd == "hyprland-config":
        print(hyprland_config(args.syntax))
        return 0
    if cmd == "sway-config":
        print(sway_config())
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
        from gamebuddy.memory import Store

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
