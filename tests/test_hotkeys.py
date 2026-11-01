import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from gamebuddy.config import HotkeyConfig
from gamebuddy.hotkeys import apply_hypr_bindings, binding_to_sequence, hypr_bindings, sequence_to_binding


def test_shortcut_capture_and_modes():
    assert sequence_to_binding("Ctrl+Alt+P") == "CTRL ALT, P"
    assert binding_to_sequence("CTRL ALT, P") == "Ctrl+Alt+P"
    cfg = HotkeyConfig()
    assert "ptt start" in hypr_bindings(cfg, True)
    assert "release = true" in hypr_bindings(cfg, True)
    cfg.mode = "toggle"
    assert "ptt toggle" in hypr_bindings(cfg, True)
    assert "ptt stop" not in hypr_bindings(cfg, True)
    with pytest.raises(ValueError):
        sequence_to_binding('Alt+";exec')


def test_owned_bindings_update_and_conflicts(tmp_path, monkeypatch):
    from gamebuddy import hotkeys

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    p = tmp_path / "hypr/gamebuddy.lua"
    p.parent.mkdir()
    old = HotkeyConfig()
    original = "-- keep rule\n" + hypr_bindings(old, True) + "-- keep footer\n"
    p.write_text(original)
    conflicts = []

    def run(cmd, **kwargs):
        return SimpleNamespace(stdout=json.dumps(conflicts) if "-j" in cmd else "", returncode=0)

    monkeypatch.setattr(hotkeys.subprocess, "run", run)
    new = replace(old, push_to_talk="CTRL ALT, P", mode="toggle")
    assert apply_hypr_bindings(new, old)
    assert "ptt toggle" in p.read_text() and p.read_text().endswith("-- keep footer\n")
    assert "-- keep rule" in p.read_text()
    conflicts.append({"modmask": 8, "key": "Q", "description": "Existing action"})
    unchanged = p.read_text()
    with pytest.raises(ValueError, match="déjà utilisé"):
        apply_hypr_bindings(replace(new, push_to_talk="ALT, Q"), new)
    assert p.read_text() == unchanged

    def broken(cmd, **kwargs):
        return SimpleNamespace(stdout="bad config" if "configerrors" in cmd else "[]", returncode=0)

    monkeypatch.setattr(hotkeys.subprocess, "run", broken)
    with pytest.raises(ValueError, match="bad config"):
        apply_hypr_bindings(replace(new, mode="hold"), new)
    assert p.read_text() == unchanged


def test_generated_compositor_configs_respect_toggle_mode(tmp_path):
    from gamebuddy.cli import hyprland_config, sway_config
    from gamebuddy.config import Config, save_config

    cfg = Config()
    cfg.hotkeys.mode = "toggle"
    save_config(cfg)
    for syntax in ("legacy", "v053", "lua"):
        text = hyprland_config(syntax)
        assert "ptt toggle" in text and "ptt stop" not in text
        if syntax == "lua":
            assert "hl.bind(" in text
    assert "ptt toggle" in sway_config() and "ptt stop" not in sway_config()
