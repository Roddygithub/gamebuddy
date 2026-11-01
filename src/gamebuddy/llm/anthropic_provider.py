"""Anthropic Claude backend (official SDK, streaming, tool use, vision)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gamebuddy.llm.base import ChatTurn, LLMProvider, Message, ToolCall, ToolSpec

EFFORTS = {"low", "medium", "high", "xhigh", "max"}


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self, model: str, api_key: str = "", base_url: str = "", effort: str = "low", timeout: float = 120.0
    ):
        import anthropic

        kwargs: dict[str, Any] = {"timeout": timeout, "max_retries": 2}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)
        self.model = model
        self.effort = effort if effort in EFFORTS else "low"

    # ---- conversion ------------------------------------------------------
    @staticmethod
    def _to_api(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        pending_tool_results: list[dict[str, Any]] = []

        def flush_tools() -> None:
            nonlocal pending_tool_results
            if pending_tool_results:
                out.append({"role": "user", "content": pending_tool_results})
                pending_tool_results = []

        for m in messages:
            if m.role == "tool":
                pending_tool_results.append(
                    {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content or "(empty)"}
                )
                continue
            flush_tools()
            if m.role == "user":
                blocks: list[dict[str, Any]] = []
                for img in m.images:
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": img["media_type"],
                                "data": img["data"],
                            },
                        }
                    )
                blocks.append({"type": "text", "text": m.content or "…"})
                out.append({"role": "user", "content": blocks})
            elif m.role == "assistant":
                if m.raw is not None and m.provider == "anthropic":
                    out.append({"role": "assistant", "content": m.raw})
                else:
                    blocks = []
                    if m.content:
                        blocks.append({"type": "text", "text": m.content})
                    for tc in m.tool_calls:
                        blocks.append(
                            {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                        )
                    if blocks:
                        out.append({"role": "assistant", "content": blocks})
        flush_tools()
        # Anthropic requires alternating roles; merge consecutive same-role turns.
        merged: list[dict[str, Any]] = []
        for item in out:
            if merged and merged[-1]["role"] == item["role"]:
                merged[-1]["content"] = list(merged[-1]["content"]) + list(item["content"])
            else:
                merged.append(item)
        if merged and merged[0]["role"] != "user":
            merged.insert(0, {"role": "user", "content": [{"type": "text", "text": "(session resumed)"}]})
        return merged

    @staticmethod
    def _tools(tools: list[ToolSpec] | None) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools or []
        ]

    # ---- call ------------------------------------------------------------
    def chat(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        on_text: Callable[[str], None] | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> ChatTurn:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or 2048,
            "system": system,
            "messages": self._to_api(messages),
            "output_config": {"effort": self.effort},
        }
        if tools:
            params["tools"] = self._tools(tools)
        if json_mode:
            params["system"] = system + "\n\nRespond with a single JSON object and nothing else."
        turn = ChatTurn()
        text_parts: list[str] = []
        with self.client.messages.stream(**params) as stream:
            for event in stream:
                if event.type == "content_block_delta" and getattr(event.delta, "type", "") == "text_delta":
                    text_parts.append(event.delta.text)
                    if on_text:
                        on_text(event.delta.text)
            final = stream.get_final_message()
        turn.text = "".join(text_parts)
        turn.stop_reason = final.stop_reason or ""
        turn.raw = [block.model_dump(exclude_none=True) for block in final.content]
        for block in final.content:
            if block.type == "tool_use":
                turn.tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {}))
                )
        if final.usage:
            turn.input_tokens = final.usage.input_tokens or 0
            turn.output_tokens = final.usage.output_tokens or 0
        if turn.stop_reason == "refusal" and not turn.text:
            turn.text = "(The model declined to answer this request.)"
        return turn
