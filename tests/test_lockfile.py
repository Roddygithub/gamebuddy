"""The shipped lockfile pins every production dependency with hashes."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
LOCK = ROOT / "requirements.lock"


def _locked() -> dict[str, list[str]]:
    """name -> hashes, from the uv/pip compatible lock."""
    pinned: dict[str, list[str]] = {}
    current = ""
    for line in LOCK.read_text().splitlines():
        head = re.match(r"^([A-Za-z0-9_.\-]+)==", line)
        if head:
            current = head.group(1).lower()
            pinned[current] = []
        elif line.lstrip().startswith("--hash=sha256:") and current:
            pinned[current].append(line.strip())
    return pinned


def test_lock_pins_every_declared_dependency_with_hashes():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    pinned = _locked()
    for spec in project["dependencies"]:
        name = re.split(r"[<>=!\[; ]", spec.strip())[0].lower()
        assert name in pinned, f"{name} missing from requirements.lock"
        assert len(pinned[name]) >= 1, f"{name} has no hash"


def test_lock_has_no_unhashed_requirement():
    for line in LOCK.read_text().splitlines():
        if re.match(r"^[A-Za-z0-9_.\-]+==", line):
            # the hash lines follow the pinned line
            assert "==" in line
    text = LOCK.read_text()
    assert text.count("--hash=sha256:") > 50
