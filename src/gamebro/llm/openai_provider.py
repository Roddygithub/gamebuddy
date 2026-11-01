"""OpenAI-compatible backend: OpenAI, Ollama (/v1), LM Studio, OpenRouter, Mistral…"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from gamebro.llm.base import ChatTurn, LLMProvider, Message, ToolCall, ToolSpec


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        model: str,
        api_key: str = "",
        base_url: str = "",
        temperature: float = 0.6,
        timeout: float = 120.0,
        vision: bool = True,
        name: str = "openai",
    ):
        from openai import OpenAI

        kwargs: dict[str, Any] = {"timeout": timeout, "max_retries": 2, "api_key": api_key or "not-needed"}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model
        self.temperature = temperature
        self._vision = vision
        self.name = name

    def supports_vision(self) -> bool:
        return self._vision

    @staticmethod
    def _to_api(system: str, messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            if m.role == "user":
                if m.images:
                    content: list[dict[str, Any]] = [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{i['media_type']};base64,{i['data']}"},
                        }
                        for i in m.images
                    ]
                    content.append({"type": "text", "text": m.content or "…"})
                    out.append({"role": "user", "content": content})
                else:
                    out.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                item: dict[str, Any] = {"role": "assistant", "content": m.content or None}
                if m.tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in m.tool_calls
                    ]
                out.append(item)
            elif m.role == "tool":
                out.append(
                    {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content or "(empty)"}
                )
        return out

    @staticmethod
    def _tools(tools: list[ToolSpec] | None) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
            }
            for t in tools or []
        ]

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
            "messages": self._to_api(system, messages),
            "stream": True,
            "max_tokens": max_tokens or 2048,
            "temperature": self.temperature,
        }
        if tools:
            params["tools"] = self._tools(tools)
        if json_mode:
            params["response_format"] = {"type": "json_object"}
        turn = ChatTurn()
        text_parts: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        for chunk in self.client.chat.completions.create(**params):
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta and delta.content:
                text_parts.append(delta.content)
                if on_text:
                    on_text(delta.content)
            if delta and delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] += tc.function.name
                        if tc.function.arguments:
                            slot["args"] += tc.function.arguments
            if choice.finish_reason:
                turn.stop_reason = choice.finish_reason
            usage = getattr(chunk, "usage", None)
            if usage:
                turn.input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                turn.output_tokens = getattr(usage, "completion_tokens", 0) or 0
        turn.text = "".join(text_parts)
        for idx in sorted(calls):
            slot = calls[idx]
            try:
                args = json.loads(slot["args"]) if slot["args"] else {}
            except json.JSONDecodeError:
                args = {"_raw": slot["args"]}
            turn.tool_calls.append(
                ToolCall(id=slot["id"] or f"call_{idx}", name=slot["name"], arguments=args)
            )
        return turn
