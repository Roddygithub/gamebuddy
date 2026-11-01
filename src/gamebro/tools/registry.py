"""Tools exposed to the model. Pure advice: nothing here can touch the game."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gamebro.llm.base import ToolSpec
from gamebro.tools.web import fetch_page, format_results, web_search


@dataclass
class ToolContext:
    """Callbacks the tools use to reach the app (UI + memory)."""

    pin: Callable[[str, str, str], None]  # (title, markdown, kind)
    unpin: Callable[[], None]
    remember: Callable[[str, str], None]  # (note, game)
    recall: Callable[[str], list[str]]  # query -> notes
    status: Callable[[str], None] = lambda _key: None
    web_enabled: bool = True
    current_game: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def build_tools(ctx: ToolContext) -> list[ToolSpec]:
    tools: list[ToolSpec] = []

    def _pin(args: dict[str, Any]) -> str:
        title = str(args.get("title", "")).strip()[:80] or "Pinned"
        content = str(args.get("markdown", "")).strip()
        kind = str(args.get("kind", "note"))
        if not content:
            return "Nothing to pin: markdown was empty."
        ctx.pin(title, content, kind)
        return f"Pinned '{title}'. It stays visible until replaced or removed."

    tools.append(
        ToolSpec(
            name="pin_content",
            description=(
                "Pin content on screen next to the game so the player can keep it visible: a build, "
                "a checklist, a comparison table, a rotation, a map note, a link or a YouTube URL. "
                "Use GitHub-flavored Markdown. Pinned content replaces the previous pin."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title (max 80 chars)."},
                    "markdown": {"type": "string", "description": "Markdown body: lists, tables, links."},
                    "kind": {
                        "type": "string",
                        "enum": ["note", "build", "checklist", "table", "link", "video"],
                        "description": "Content kind, affects the icon only.",
                    },
                },
                "required": ["title", "markdown"],
                "additionalProperties": False,
            },
            handler=_pin,
        )
    )

    def _unpin(_args: dict[str, Any]) -> str:
        ctx.unpin()
        return "Pinned content removed."

    tools.append(
        ToolSpec(
            name="unpin_content",
            description="Remove the currently pinned content when the player asks for it.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=_unpin,
        )
    )

    def _remember(args: dict[str, Any]) -> str:
        note = str(args.get("note", "")).strip()
        if not note:
            return "Nothing to remember."
        ctx.remember(note[:500], str(args.get("game", "")) or ctx.current_game)
        return "Saved to long-term memory."

    tools.append(
        ToolSpec(
            name="remember",
            description=(
                "Save a durable fact about the player for future sessions: preferences, main characters, "
                "goals, skill level per mechanic, things they asked you to remember. One short sentence."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "note": {"type": "string"},
                    "game": {"type": "string", "description": "Game the note relates to, if any."},
                },
                "required": ["note"],
                "additionalProperties": False,
            },
            handler=_remember,
        )
    )

    def _recall(args: dict[str, Any]) -> str:
        notes = ctx.recall(str(args.get("query", "")))
        return "\n".join(f"- {n}" for n in notes) if notes else "No matching memory."

    tools.append(
        ToolSpec(
            name="recall",
            description="Search long-term memory about this player (older than the current conversation).",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_recall,
        )
    )

    if ctx.web_enabled:

        def _search(args: dict[str, Any]) -> str:
            ctx.status("searching")
            q = str(args.get("query", "")).strip()
            if not q:
                return "Empty query."
            try:
                return format_results(web_search(q, max_results=int(args.get("max_results", 5))))
            except Exception as exc:  # noqa: BLE001
                return f"Search failed: {exc}"

        tools.append(
            ToolSpec(
                name="web_search",
                description=(
                    "Search the web for recent information: patch notes, current meta, builds, guides, "
                    "wiki pages. Prefer it over memory for anything that changes with game versions."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=_search,
            )
        )

        def _fetch(args: dict[str, Any]) -> str:
            ctx.status("searching")
            try:
                return fetch_page(str(args.get("url", "")))
            except Exception as exc:  # noqa: BLE001
                return f"Fetch failed: {exc}"

        tools.append(
            ToolSpec(
                name="fetch_page",
                description="Read the text of a web page (guide, wiki, patch notes) found via web_search.",
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                    "additionalProperties": False,
                },
                handler=_fetch,
            )
        )
    return tools


def run_tool(tools: list[ToolSpec], name: str, args: dict[str, Any]) -> str:
    for t in tools:
        if t.name == name:
            try:
                return t.handler(args) or "(done)"
            except Exception as exc:  # noqa: BLE001
                return f"Tool error: {exc}"
    return f"Unknown tool: {name}"


def tool_result_preview(result: str, limit: int = 200) -> str:
    text = json.dumps(result) if not isinstance(result, str) else result
    return text if len(text) <= limit else text[:limit] + "…"
