"""ChatGPT Plus/Pro backend through the official OpenAI Codex CLI (`codex exec`).

No API key: Codex signs in with the user's ChatGPT account (`codex login`) and
usage counts against the subscription's limits. Each call runs one
non-interactive `codex exec` with the prompt on stdin, an optional screenshot
(`-i`) and a JSON output schema. Tools are emulated with an "actions" envelope:
the model lists actions, GameBuddy runs them and sends the results back on the
next call — so `Kin`'s tool loop works unchanged.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gamebuddy.llm.base import ChatTurn, LLMProvider, Message, ToolCall, ToolSpec
from gamebuddy.llm.catalog import CODEX_EFFORTS

ENVELOPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reply": {
            "type": "string",
            "description": "What to say to the player. Empty if actions are needed first.",
        },
        "actions": {
            "type": "array",
            "description": "Actions to run before answering (results arrive on the next turn).",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments": {
                        "type": "string",
                        "description": "The action's arguments as a JSON object, encoded as a string.",
                    },
                },
                "required": ["name", "arguments"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reply", "actions"],
    "additionalProperties": False,
}


class CodexError(RuntimeError):
    pass


class CodexProvider(LLMProvider):
    name = "codex"

    def __init__(self, model: str = "", effort: str = "low", binary: str = "codex", timeout: float = 240.0):
        self.model = model
        self.effort = effort if effort in CODEX_EFFORTS else "low"
        self.binary = binary or "codex"
        self.timeout = timeout

    def supports_vision(self) -> bool:
        return True

    # ---- prompt rendering ----------------------------------------------------
    @staticmethod
    def render_transcript(messages: list[Message]) -> str:
        lines: list[str] = []
        for m in messages:
            if m.role == "user":
                tag = "[user, screenshot attached]" if m.images else "[user]"
                lines.append(f"{tag}\n{m.content}")
            elif m.role == "assistant":
                if m.content:
                    lines.append(f"[assistant]\n{m.content}")
                for tc in m.tool_calls:
                    lines.append(
                        f"[assistant action] {tc.name}({json.dumps(tc.arguments, ensure_ascii=False)})"
                    )
            elif m.role == "tool":
                lines.append(f"[action result]\n{m.content}")
        return "\n\n".join(lines)

    @staticmethod
    def render_tools(tools: list[ToolSpec]) -> str:
        out = ['Available actions (list them in "actions"; GameBuddy runs them and sends the results back):']
        for t in tools:
            props = t.parameters.get("properties", {})
            args = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in props.items())
            out.append(f"- {t.name}({args}) — {t.description}")
        return "\n".join(out)

    def build_prompt(
        self, system: str, messages: list[Message], tools: list[ToolSpec] | None, json_mode: bool
    ) -> str:
        parts = [
            "You are answering inside GameBuddy, a gaming companion widget. Do NOT run shell commands, read or write files, "
            "or inspect this directory: you only chat. The working directory is empty on purpose.",
            "<instructions>\n" + system + "\n</instructions>",
        ]
        if tools:
            parts.append(self.render_tools(tools))
            parts.append(
                'Respond with the JSON object required by the schema: put your spoken answer in "reply" (short, '
                'conversational, same language as the player). If you need an action\'s result first, leave "reply" '
                "empty and list the actions; after results arrive you will be asked again. Use pin_content for anything "
                "worth keeping on screen. Never invent action results."
            )
        elif json_mode:
            parts.append("Respond with exactly one JSON object and nothing else.")
        parts.append("<conversation>\n" + self.render_transcript(messages) + "\n</conversation>")
        parts.append(
            "Now respond to the latest user message." if not json_mode else "Now produce the JSON object."
        )
        return "\n\n".join(parts)

    # ---- call -------------------------------------------------------------------
    def chat(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        on_text: Callable[[str], None] | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> ChatTurn:
        if shutil.which(self.binary) is None:
            raise CodexError("codex_not_installed")
        prompt = self.build_prompt(system, messages, tools, json_mode)
        with tempfile.TemporaryDirectory(prefix="gamebuddy-codex-") as tmp:
            tmpdir = Path(tmp)
            out_file = tmpdir / "last.txt"
            cmd = [
                self.binary,
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                # Keep user-installed MCPs/plugins/apps and tool overrides out
                # of Buddy's model session; authentication still uses CODEX_HOME.
                "--ignore-user-config",
                "-c",
                f'model_reasoning_effort="{self.effort}"',
                "-o",
                str(out_file),
            ]
            # Buddy runs its own tools. Keep Codex chat-only: its shell, local
            # image reader and web search are unnecessary. The explicitly
            # attached -i screenshot remains the only image sent to the model.
            cmd += [
                "-c",
                "features.shell_tool=false",
                "-c",
                "tools.view_image=false",
                "-c",
                "tools.web_search=false",
                "-c",
                "apps._default.enabled=false",
            ]
            if self.model:
                cmd += ["-m", self.model]
            if tools:
                schema = tmpdir / "schema.json"
                schema.write_text(json.dumps(ENVELOPE_SCHEMA))
                cmd += ["--output-schema", str(schema)]
            last_user = next((m for m in reversed(messages) if m.role == "user"), None)
            if last_user and last_user.images:
                import base64

                img = last_user.images[-1]
                ext = "png" if "png" in img["media_type"] else "jpg"
                img_path = tmpdir / f"screenshot.{ext}"
                img_path.write_bytes(base64.standard_b64decode(img["data"]))
                cmd += ["-i", str(img_path)]
            cmd.append("-")  # prompt from stdin
            env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY",)}  # force ChatGPT auth
            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=str(tmpdir),
                    env=env,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise CodexError("codex_timeout") from exc
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()
                low = err.lower()
                if "login" in low or "auth" in low or "unauthorized" in low or "sign in" in low:
                    raise CodexError("codex_not_logged_in")
                raise CodexError(f"codex_failed: {err[-400:]}")
            text = out_file.read_text().strip() if out_file.exists() else (proc.stdout or "").strip()
        turn = ChatTurn(stop_reason="end_turn")
        if tools:
            reply, calls = parse_envelope(text)
            turn.text = reply
            turn.tool_calls = calls
        else:
            turn.text = text
        if on_text and turn.text:
            on_text(turn.text)
        return turn


def parse_envelope(text: str) -> tuple[str, list[ToolCall]]:
    """Parse {"reply": str, "actions": [{"name", "arguments"}]} — tolerant of fences and prose."""
    cleaned = text.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        return cleaned, []
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return cleaned, []
    if not isinstance(data, dict):
        return cleaned, []
    reply = str(data.get("reply") or "")
    calls: list[ToolCall] = []
    for i, action in enumerate(data.get("actions") or []):
        if not isinstance(action, dict) or not action.get("name"):
            continue
        args = action.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {"value": args}
        calls.append(ToolCall(id=f"act_{i}", name=str(action["name"]), arguments=args))
    return reply, calls


def codex_logged_in() -> bool:
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return (home / "auth.json").is_file()
