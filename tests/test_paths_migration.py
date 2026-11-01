"""0.1.x → 0.2 rename: legacy gamebro dirs are migrated into gamebuddy dirs."""

import os
import stat

import pytest

from gamebuddy import paths
from gamebuddy.memory import Store


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


def test_default_store_protects_data_directory_and_database(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    database = paths.db_file()
    database.parent.mkdir(parents=True)
    database.write_bytes(b"")
    database.chmod(0o644)
    old_umask = os.umask(0o022)
    try:
        store = Store()
    finally:
        os.umask(old_umask)

    try:
        assert stat.S_IMODE(paths.data_dir().stat().st_mode) == 0o700
        assert stat.S_IMODE(paths.db_file().stat().st_mode) == 0o600
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = database.with_name(database.name + suffix)
            if sidecar.exists():
                assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600
    finally:
        store.close()


def test_existing_database_and_sqlite_sidecars_are_repaired(tmp_path):
    database = tmp_path / "gamebuddy.db"
    files = [
        database,
        *(database.with_name(database.name + suffix) for suffix in ("-wal", "-shm", "-journal")),
    ]
    for path in files:
        path.write_bytes(b"existing private data")
        path.chmod(0o644)

    paths.secure_database_files(database)

    assert [stat.S_IMODE(path.stat().st_mode) for path in files] == [0o600] * len(files)


def test_database_symlink_is_rejected(tmp_path):
    target = tmp_path / "other-file"
    target.write_text("not a database")
    database = tmp_path / "gamebuddy.db"
    database.symlink_to(target)

    with pytest.raises(OSError, match="regular file"):
        paths.secure_database_files(database)

    assert target.read_text() == "not a database"
