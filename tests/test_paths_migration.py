"""0.1.x → 0.2 rename: legacy gamebro dirs are migrated into gamebuddy dirs."""

from gamebuddy import paths


def test_legacy_dirs_are_migrated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    (tmp_path / "cfg" / "gamebro").mkdir(parents=True)
    (tmp_path / "cfg" / "gamebro" / "config.toml").write_text("[general]\n")
    (tmp_path / "data" / "gamebro").mkdir(parents=True)
    (tmp_path / "data" / "gamebro" / "gamebro.db").write_bytes(b"db")
    (tmp_path / "data" / "gamebuddy" / "venv").mkdir(parents=True)  # created by install.sh first
    paths.ensure_dirs()
    assert paths.config_file().read_text() == "[general]\n"
    assert paths.db_file().read_bytes() == b"db"
    assert not (tmp_path / "cfg" / "gamebro" / "config.toml").exists()
    paths.ensure_dirs()  # idempotent
