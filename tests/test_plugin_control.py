import json
import os
import subprocess
from pathlib import Path

CONTROL = Path(__file__).parents[1] / "plugin-control.sh"


def test_plugin_missing_engine_and_running_engine(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    env = {**os.environ, "HOME": str(tmp_path), "PATH": str(bindir)}

    def run(*args):
        return subprocess.run(["/bin/sh", str(CONTROL), *args], env=env, capture_output=True, text=True)

    assert json.loads(run("status").stdout) == {"ok": False, "installed": False}
    assert run("start").returncode == 127
    engine = bindir / "gamebuddy"
    engine.write_text(
        '#!/bin/sh\nif [ "$1" = status ]; then printf \'{"ok":true,"model":"demo"}\\n\'; else printf "%s\\n" "$*"; fi\n'
    )
    engine.chmod(0o755)
    assert json.loads(run("status").stdout)["model"] == "demo"
    assert run("start").stdout.strip() == "show"
    assert run("ai-settings").stdout.strip() == "ai-settings"
    assert run("unsupported").returncode == 2


def test_uninstall_removes_only_own_includes_and_keeps_user_data(tmp_path):
    root = Path(__file__).parents[1]
    home = tmp_path / "home"
    hypr = home / ".config/hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.lua").write_text('require("hypr.monitors")\nrequire("hypr.gamebuddy")\n')
    (hypr / "gamebuddy.lua").write_text("-- owned\n")
    data = home / ".local/share/gamebuddy"
    data.mkdir(parents=True)
    (data / "gamebuddy.db").write_text("keep database")
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "systemctl").write_text("#!/bin/sh\nexit 0\n")
    (stub / "systemctl").chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "PATH": f"{stub}:/usr/bin",
    }
    result = subprocess.run(
        ["/bin/bash", str(root / "install.sh"), "uninstall"], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert (hypr / "hyprland.lua").read_text() == 'require("hypr.monitors")\n'
    assert not (hypr / "gamebuddy.lua").exists()
    assert (data / "gamebuddy.db").read_text() == "keep database"
    assert list(hypr.glob("hyprland.lua.bak.*"))
