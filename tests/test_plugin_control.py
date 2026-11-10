import json
import os
import subprocess
from pathlib import Path

CONTROL = Path(__file__).parents[1] / "plugin-control.sh"


def test_plugin_missing_engine_and_running_engine(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # The script shells out to coreutils (timeout, head) like a real session does.
    env = {**os.environ, "HOME": str(tmp_path), "PATH": f"{bindir}:/usr/bin:/bin"}

    def run(*args):
        return subprocess.run(["/bin/sh", str(CONTROL), *args], env=env, capture_output=True, text=True)

    assert json.loads(run("status").stdout) == {"ok": False, "installed": False}
    assert run("start").returncode == 127
    log = tmp_path / "calls.log"
    engine = bindir / "gamebuddy"
    engine.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> {log}\n'
        'if [ "$1" = status ]; then printf \'{"ok":true,"model":"demo"}\\n\'; fi\n'
    )
    engine.chmod(0o755)
    assert json.loads(run("status").stdout)["model"] == "demo"
    # The bar never parses these answers, so the script drops them and only runs them.
    assert run("start").returncode == 0
    assert run("ai-settings").returncode == 0
    calls = log.read_text().splitlines()
    assert "show" in calls
    assert "ai-settings" in calls
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
