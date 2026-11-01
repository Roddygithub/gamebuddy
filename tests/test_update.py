"""Self-update: version compare, cached check, update flow with git/install stubbed."""

import json

import pytest

from gamebuddy import __version__, update
from gamebuddy.cli import main


def test_parse_version():
    assert update.parse_version("v0.2.1") == (0, 2, 1)
    assert update.parse_version("1.10") > update.parse_version("1.9.9")
    assert update.parse_version("") == (0,)


def _fake_latest(version):
    return lambda timeout=6.0: {"tag": f"v{version}", "version": version, "url": "u", "notes": ""}


def test_check_reports_newer_and_caches(monkeypatch):
    info = update.check_for_update(force=True, fetch=_fake_latest("99.0.0"))
    assert info["available"] and info["latest"] == "99.0.0" and info["installed"] == __version__
    cached = json.loads(update._cache_file().read_text())
    assert cached["latest"] == "99.0.0"

    def boom(timeout=6.0):
        raise AssertionError("network must not be hit within the cache window")

    assert update.check_for_update(fetch=boom)["latest"] == "99.0.0"


def test_check_same_version_not_available():
    info = update.check_for_update(force=True, fetch=_fake_latest(__version__))
    assert not info["available"]


def test_cli_check_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(update, "fetch_latest", _fake_latest("99.0.0"))
    assert main(["update", "--check"]) == 10
    assert "99.0.0" in capsys.readouterr().out
    monkeypatch.setattr(update, "fetch_latest", _fake_latest(__version__))
    assert main(["update", "--check"]) == 0


def test_run_update_flow(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(update, "fetch_latest", _fake_latest("99.0.0"))
    monkeypatch.setattr(update.shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(update, "source_dir", lambda: tmp_path / "src")
    monkeypatch.setattr(update, "_restart_widget", lambda log=print: calls.append("restart"))

    def fake_git(*args, cwd):
        calls.append(("git", args[0]))
        if args[0] == "clone":
            (tmp_path / "src" / ".git").mkdir(parents=True)

    monkeypatch.setattr(update, "_git", fake_git)

    class Proc:
        returncode = 0

    monkeypatch.setattr(
        update.subprocess, "run", lambda *a, **k: calls.append(("install", a[0][-1])) or Proc()
    )
    assert update.run_update(log=lambda *_: None) == 0
    assert ("git", "clone") in calls and ("git", "checkout") in calls and "restart" in calls
    assert any(c[0] == "install" and c[1].endswith("install.sh") for c in calls if isinstance(c, tuple))


def test_run_update_noop_when_current(monkeypatch):
    monkeypatch.setattr(update, "fetch_latest", _fake_latest(__version__))
    monkeypatch.setattr(update.shutil, "which", lambda name: "/usr/bin/git")
    assert update.run_update(only_if_available=True, log=lambda *_: None) == 0


def test_run_update_requires_git(monkeypatch):
    monkeypatch.setattr(update.shutil, "which", lambda name: None)
    with pytest.raises(update.UpdateError):
        update.run_update()


def test_update_preserves_non_git_source(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    valuable = source / "notes.txt"
    valuable.write_text("keep me")
    monkeypatch.setattr(update, "fetch_latest", _fake_latest("99.0.0"))
    monkeypatch.setattr(update.shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(update, "source_dir", lambda: source)
    with pytest.raises(update.UpdateError, match="refusing to replace"):
        update.run_update(log=lambda *_: None)
    assert valuable.read_text() == "keep me"


def test_update_recognizes_worktree(monkeypatch, tmp_path):
    (tmp_path / ".git").write_text("gitdir: /some/worktree")
    calls = []
    monkeypatch.setattr(update, "fetch_latest", _fake_latest("99.0.0"))
    monkeypatch.setattr(update.shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(update, "source_dir", lambda: tmp_path)
    monkeypatch.setattr(update, "_git", lambda *args, **kw: calls.append(args))
    monkeypatch.setattr(update, "_restart_widget", lambda log: None)
    monkeypatch.setattr(update.subprocess, "run", lambda *a, **kw: type("Proc", (), {"returncode": 0})())
    assert update.run_update(log=lambda *_: None) == 0
    assert [c[0] for c in calls] == ["fetch", "checkout"]
    assert calls[-1][-1] == "refs/tags/v99.0.0"
