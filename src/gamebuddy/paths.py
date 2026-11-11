"""XDG-aware filesystem locations."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from gamebuddy import APP_ID


def _xdg(var: str, default: Path) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else default


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", Path.home() / ".config") / APP_ID


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP_ID


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", Path.home() / ".cache") / APP_ID


def runtime_dir() -> Path:
    value = os.environ.get("XDG_RUNTIME_DIR")
    if value and Path(value).is_dir():
        return Path(value)
    return cache_dir()


def config_file() -> Path:
    return config_dir() / "config.toml"


def db_file() -> Path:
    return data_dir() / "gamebuddy.db"


def coach_frames_dir() -> Path:
    return data_dir() / "coach_frames"


def socket_path() -> Path:
    override = os.environ.get("GAMEBUDDY_SOCKET")
    return Path(override) if override else runtime_dir() / "gamebuddy.sock"


LEGACY_APP_ID = "gamebro"  # name used by releases <= 0.1.1


def _migrate_legacy(new: Path) -> None:
    """Move files from ~/.config/gamebro (etc.) into the gamebuddy dir the first time 0.2 runs."""
    old = new.parent / LEGACY_APP_ID
    if not old.is_dir() or old == new:
        return
    try:
        new.mkdir(parents=True, exist_ok=True)
        for src in old.iterdir():
            name = src.name.replace(LEGACY_APP_ID, APP_ID) if src.name.startswith(LEGACY_APP_ID) else src.name
            dst = new / name
            if not dst.exists() and src.name != "venv":
                src.rename(dst)
    except OSError:
        pass


def ensure_dirs() -> None:
    for d in (config_dir(), data_dir(), cache_dir()):
        _migrate_legacy(d)
        d.mkdir(parents=True, exist_ok=True)

    # Conversations and long-term notes are private user data. Restrict the
    # app directory itself as well as the SQLite files, so WAL/SHM files
    # remain private even if SQLite creates them with a permissive umask.
    data = data_dir()
    if not stat.S_ISDIR(data.lstat().st_mode):
        raise NotADirectoryError(f"GameBuddy data path is not a directory: {data}")
    data.chmod(0o700)


def secure_database_files(database: Path) -> None:
    """Create/protect a SQLite database and repair existing sidecar modes.

    Refuse symlinks and special files so SQLite cannot follow a database path
    outside the protected app directory. Existing files are chmodded before
    opening them, including stale WAL, SHM, and rollback-journal files.
    """

    def protect(path: Path, *, create: bool = False) -> None:
        flags = os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            if not create:
                return
            # O_EXCL prevents an unexpected path from being substituted at
            # creation time; O_NOFOLLOW also rejects a symlink on Linux.
            fd = os.open(path, flags | os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        else:
            if not stat.S_ISREG(mode):
                raise OSError(f"SQLite path is not a regular file: {path}")
            # chmod can repair a mode-000 file before it is opened.
            path.chmod(0o600)
            fd = os.open(path, flags | os.O_RDONLY)

        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError(f"SQLite path is not a regular file: {path}")
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)

    protect(database, create=True)
    for suffix in ("-wal", "-shm", "-journal"):
        protect(database.with_name(database.name + suffix))
