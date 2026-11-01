"""Provider-neutral chat types.

History is kept in a neutral shape and converted by each provider. The raw
provider payload of an assistant turn is kept (``raw``) so a provider can replay
its own turns verbatim (Anthropic needs thinking/tool_use blocks back as-is).
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema (type: object)
    handler: Callable[[dict[str, Any]], str]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    role: str  # system | user | assistant | tool
    content: str = ""
    images: list[dict[str, str]] = field(default_factory=list)  # {"media_type":..., "data": b64}
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""  # for role == tool
    raw: Any = None  # provider-specific replay payload for assistant turns
    provider: str = ""  # provider that produced ``raw``

    def to_record(self) -> dict[str, Any]:
        """Serializable form for the SQLite store (images dropped on purpose)."""
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": [tc.__dict__ for tc in self.tool_calls],
            "tool_call_id": self.tool_call_id,
            "had_images": bool(self.images),
        }

    @classmethod
    def from_record(cls, rec: dict[str, Any]) -> Message:
        return cls(
            role=rec.get("role", "user"),
            content=rec.get("content", ""),
            tool_calls=[ToolCall(**tc) for tc in rec.get("tool_calls", [])],
            tool_call_id=rec.get("tool_call_id", ""),
        )


@dataclass
class ChatTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


def image_part(data: bytes, media_type: str = "image/jpeg") -> dict[str, str]:
    return {"media_type": media_type, "data": base64.standard_b64encode(data).decode("ascii")}


class LLMProvider:
    """Interface implemented by each backend."""

    name = "base"
    model = ""

    def chat(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        on_text: Callable[[str], None] | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> ChatTurn:
        raise NotImplementedError

    def supports_vision(self) -> bool:
        return True
