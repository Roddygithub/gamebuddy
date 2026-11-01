"""Self-update: check GitHub releases, pull the tagged source and re-run install.sh.

Policy lives in `general.auto_update`:
  off    — never check
  notify — check once a day, show a bubble in the widget (default)
  auto   — the daily systemd timer installs new releases by itself
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

from gamebuddy import __version__
from gamebuddy.paths import cache_dir, data_dir

REPO = "Roddygithub/gamebuddy"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
GIT_URL = f"https://github.com/{REPO}.git"
CHECK_INTERVAL_S = 24 * 3600


class UpdateError(RuntimeError):
    pass


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def fetch_latest(timeout: float = 6.0) -> dict:
    """Return {'tag', 'version', 'url', 'notes'} for the latest GitHub release."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"gamebuddy/{__version__}"}
    resp = httpx.get(RELEASES_API, headers=headers, timeout=timeout, follow_redirects=True)
    if resp.status_code == 404:  # no release yet → fall back to tags
        tags_resp = httpx.get(f"https://api.github.com/repos/{REPO}/tags", headers=headers, timeout=timeout)
        tags_resp.raise_for_status()
        tags = tags_resp.json()
        if not tags:
            raise UpdateError("no releases or tags")
        tag = tags[0]["name"]
        return {"tag": tag, "version": tag.lstrip("v"), "url": f"https://github.com/{REPO}", "notes": ""}
    resp.raise_for_status()
    data = resp.json()
    tag = data["tag_name"]
    return {
        "tag": tag,
        "version": tag.lstrip("v"),
        "url": data.get("html_url", f"https://github.com/{REPO}/releases"),
        "notes": data.get("body") or "",
    }


def _cache_file() -> Path:
    return cache_dir() / "update-check.json"


def check_for_update(force: bool = False, fetch=None) -> dict:
    """Cached daily check. Returns {'installed', 'latest', 'available', 'url', 'checked_at'}."""
    fetch = fetch or fetch_latest
    cache = _cache_file()
    now = time.time()
    if not force and cache.is_file():
        try:
            cached = json.loads(cache.read_text())
            if (
                now - cached.get("checked_at", 0) < CHECK_INTERVAL_S
                and cached.get("installed") == __version__
            ):
                return cached
        except (OSError, ValueError):
            pass
    latest = fetch()
    result = {
        "installed": __version__,
        "latest": latest["version"],
        "tag": latest["tag"],
        "url": latest["url"],
        "available": parse_version(latest["version"]) > parse_version(__version__),
        "checked_at": now,
    }
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result))
    except OSError:
        pass
    return result


def source_dir() -> Path:
    """Where install.sh was run from (recorded by install.sh), else a clone we manage."""
    marker = data_dir() / "source_dir"
    if marker.is_file():
        recorded = Path(marker.read_text().strip())
        if (recorded / "install.sh").is_file():
            return recorded
    return data_dir() / "src"


def _git(*args: str, cwd: Path) -> None:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise UpdateError(f"git {args[0]} failed: {proc.stderr.strip()[-300:]}")


def run_update(only_if_available: bool = False, quiet: bool = False, log=print) -> int:
    """Fetch the latest tag into the source dir, re-run install.sh, restart the widget."""
    if not shutil.which("git"):
        raise UpdateError("git is required for updates (pacman -S git)")
    info = check_for_update(force=True)
    if not info["available"]:
        if not quiet:
            log(f"gamebuddy {info['installed']} is up to date")
        if only_if_available:
            return 0
    tag = info["tag"]
    src = source_dir()
    if not (src / ".git").exists():  # .git is a file in a linked worktree
        src.parent.mkdir(parents=True, exist_ok=True)
        if src.exists() and (not src.is_dir() or any(src.iterdir())):
            raise UpdateError(f"refusing to replace non-git source directory: {src}")
        log(f"cloning {GIT_URL} → {src}")
        _git("clone", "--quiet", GIT_URL, str(src), cwd=src.parent)
    log(f"fetching {tag}")
    _git("fetch", "--quiet", "--tags", "--force", "origin", cwd=src)
    _git("checkout", "--quiet", "--detach", f"refs/tags/{tag}", cwd=src)
    log("running install.sh")
    env = {**os.environ, "GAMEBUDDY_UPDATING": "1"}
    proc = subprocess.run(["bash", str(src / "install.sh")], cwd=src, env=env, check=False)
    if proc.returncode != 0:
        raise UpdateError(f"install.sh exited with {proc.returncode}")
    _restart_widget(log)
    log(f"updated to {tag}")
    return 0


def _restart_widget(log=print) -> None:
    from gamebuddy.ipc import is_running, send_command

    unit_active = (
        subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", "gamebuddy.service"], check=False
        ).returncode
        == 0
        if shutil.which("systemctl")
        else False
    )
    if unit_active:
        subprocess.run(["systemctl", "--user", "restart", "gamebuddy.service"], check=False)
        log("restarted gamebuddy.service")
        return
    if is_running():
        try:
            send_command({"cmd": "quit"})
        except OSError:
            pass
        time.sleep(1.0)
        exe = shutil.which("gamebuddy") or sys.argv[0]
        subprocess.Popen([exe], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("restarted the widget")
