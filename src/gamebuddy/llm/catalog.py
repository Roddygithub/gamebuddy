"""Optional local Codex catalogue; no network or CLI startup from a tray menu."""

from __future__ import annotations

import json
import os
from pathlib import Path


def codex_models() -> list[dict]:
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    try:
        data = json.loads((home / "models_cache.json").read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        return []
    return [
        m
        for m in data["models"]
        if isinstance(m, dict)
        and isinstance(m.get("slug"), str)
        and m["slug"]
        and m.get("visibility") == "list"
    ]


def reasoning_levels(provider: str, model: str) -> list[str]:
    if provider == "codex":
        for item in codex_models():
            if item["slug"] == model:
                levels = item.get("supported_reasoning_levels", [])
                if isinstance(levels, list):
                    result = [
                        r["effort"]
                        for r in levels
                        if isinstance(r, dict) and r.get("effort") in CODEX_EFFORTS
                    ]
                    if result:
                        return result
        return ["low", "medium", "high", "xhigh"]
    if provider == "anthropic":
        return ["low", "medium", "high", "xhigh", "max"]
    return []


CODEX_EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
