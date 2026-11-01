"""Portal backend (fake spectacle / parsed portal reply), session detection, sway config, Ollama no-tools fallback."""

import os
import stat

import pytest

from gamebuddy.capture.base import CaptureError, Rect, WindowInfo, detect_session, get_backend, overlay_mask
from gamebuddy.capture.portal import PortalBackend, read_portal_result
from gamebuddy.cli import main, sway_config, sway_key

PNG = b"\x89PNG\r\n\x1a\nfakepng"


def test_detect_session_prefers_portal_on_gnome_kde(monkeypatch):
    for var in ("HYPRLAND_INSTANCE_SIGNATURE", "SWAYSOCK", "DISPLAY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr("gamebuddy.capture.base.platform.system", lambda: "Linux")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert detect_session() == "portal"
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    assert detect_session() == "portal"
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "niri")
    monkeypatch.setattr("gamebuddy.capture.base.have", lambda tool: tool == "grim")
    assert detect_session() == "wlroots"
    assert isinstance(get_backend("portal"), PortalBackend)


def test_whole_screen_mask_is_absolute():
    screen = WindowInfo(id="output", title="Whole screen", app_id="", rect=Rect(0, 0, 0, 0))
    assert overlay_mask(screen, Rect(1500, 60, 260, 96)) == Rect(1500, 60, 260, 96)


def test_capture_through_fake_spectacle(tmp_path, monkeypatch):
    script = tmp_path / "spectacle"
    script.write_text(
        "#!/usr/bin/env bash\nwhile [ $# -gt 1 ]; do shift; done\n"
        "printf '\\x89PNG\\r\\n\\x1a\\nfakepng' > \"$1\"\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    backend = PortalBackend()
    assert backend.available()
    [win] = backend.list_windows()
    assert backend.capture(win) == PNG


def test_read_portal_result(tmp_path):
    shot = tmp_path / "Screenshot from 2026.png"
    shot.write_bytes(PNG)
    assert read_portal_result(0, {"uri": ("s", shot.as_uri())}) == PNG
    assert not shot.exists()  # consumed
    with pytest.raises(CaptureError, match="portal_denied"):
        read_portal_result(1, {})
    with pytest.raises(CaptureError):
        read_portal_result(0, {})


def test_sway_key_and_config(capsys):
    assert sway_key("ALT, V") == "Mod1+v"
    assert sway_key("SUPER SHIFT, B") == "Mod4+Shift+b"
    text = sway_config()
    assert 'for_window [app_id="gamebuddy"] floating enable, sticky enable' in text
    assert "bindsym --release Mod1+v exec gamebuddy ptt stop" in text
    assert main(["sway-config"]) == 0
    assert "bindsym Mod1+b exec gamebuddy toggle" in capsys.readouterr().out


def test_openai_provider_retries_without_tools():
    from gamebuddy.llm.base import Message, ToolSpec
    from gamebuddy.llm.openai_provider import OpenAIProvider

    class Delta:
        content = "ok"
        tool_calls = None

    class Choice:
        delta = Delta()
        finish_reason = "stop"

    class Chunk:
        choices = [Choice()]

    class Completions:
        calls: list[dict] = []

        def create(self, **params):
            self.calls.append(params)
            if "tools" in params:
                raise RuntimeError("registry.ollama.ai/library/gemma3 does not support tools")
            return iter([Chunk()])

    class Client:
        class chat:  # noqa: N801
            completions = Completions()

    p = OpenAIProvider.__new__(OpenAIProvider)
    p.model, p.temperature, p.client, p.name = "gemma3", 0.3, Client(), "ollama"
    tool = ToolSpec(
        name="web_search",
        description="d",
        parameters={"type": "object", "properties": {}},
        handler=lambda a: "",
    )
    turn = p.chat("sys", [Message(role="user", content="hi")], tools=[tool])
    assert turn.text == "ok"
    assert len(Completions.calls) == 2 and "tools" not in Completions.calls[1]
    p.chat("sys", [Message(role="user", content="again")], tools=[tool])
    assert "tools" not in Completions.calls[2]  # remembered
