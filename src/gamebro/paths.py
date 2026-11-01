"""XDG-aware filesystem locations."""

from __future__ import annotations

import os
from pathlib import Path

from gamebro import APP_ID


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
    return data_dir() / "gamebro.db"


def socket_path() -> Path:
    override = os.environ.get("GAMEBRO_SOCKET")
    return Path(override) if override else runtime_dir() / "gamebro.sock"


def ensure_dirs() -> None:
    for d in (config_dir(), data_dir(), cache_dir()):
        d.mkdir(parents=True, exist_ok=True)
