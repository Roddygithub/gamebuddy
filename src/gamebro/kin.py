"""The assistant orchestrator ("Bro"): builds context, runs the tool loop, streams text.

UI-agnostic: it talks to the outside world through ``KinCallbacks``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from gamebro.config import Config
from gamebro.llm import ChatTurn, LLMProvider, Message, image_part, make_provider
from gamebro.memory import Store
from gamebro.prompts import ask_system_prompt
from gamebro.tools import ToolContext, build_tools
from gamebro.tools.registry import run_tool

log = logging.getLogger(__name__)


@dataclass
class KinCallbacks:
    on_status: Callable[[str], None] = lambda key: None  # i18n key: thinking | searching | speaking | ready
    on_text_delta: Callable[[str], None] = lambda text: None
    on_reply_done: Callable[[str], None] = lambda text: None
    on_pin: Callable[[str, str, str], None] = lambda title, md, kind: None
    on_unpin: Callable[[], None] = lambda: None
    on_memory: Callable[[str], None] = lambda note: None
    on_error: Callable[[str], None] = lambda message: None
    on_tool: Callable[[str, dict], None] = lambda name, args: None
    extra: dict = field(default_factory=dict)


class Kin:
    def __init__(
        self, cfg: Config, store: Store, callbacks: KinCallbacks, provider: LLMProvider | None = None
    ):
        self.cfg = cfg
        self.store = store
        self.cb = callbacks
        self._provider = provider
        self._lock = threading.Lock()
        self.game_title = ""
        self.language = "en"
        self.busy = False

    # ---- provider --------------------------------------------------------
    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            self._provider = make_provider(self.cfg)
        return self._provider

    def reset_provider(self) -> None:
        self._provider = None

    # ---- main entry ------------------------------------------------------
    def ask(self, text: str, screenshot: bytes | None = None, media_type: str = "image/jpeg") -> str:
        """Run one exchange. Blocking; call from a worker thread."""
        if not text.strip():
            return ""
        with self._lock:
            self.busy = True
            try:
                return self._ask(text.strip(), screenshot, media_type)
            except Exception as exc:  # noqa: BLE001
                log.exception("ask failed")
                self.cb.on_error(str(exc))
                return ""
            finally:
                self.busy = False
                self.cb.on_status("ready")

    def _ask(self, text: str, screenshot: bytes | None, media_type: str) -> str:
        self.cb.on_status("thinking")
        ctx = ToolContext(
            pin=self._pin,
            unpin=self._unpin,
            remember=self._remember,
            recall=self.store.search_memories,
            status=self.cb.on_status,
            web_enabled=self.cfg.llm.web_search,
            current_game=self.game_title,
        )
        tools = build_tools(ctx)
        provider = self.provider
        attach = bool(screenshot) and self.cfg.capture.attach_screenshot and provider.supports_vision()
        system = ask_system_prompt(
            name=self.cfg.general.assistant_name,
            language=self.language,
            personality=self.cfg.general.personality,
            game_title=self.game_title,
            memories=self.store.memories(limit=40, game=self.game_title),
            has_screenshot=attach,
            web_enabled=self.cfg.llm.web_search,
        )
        history = self.store.recent_messages(self.cfg.llm.history_messages)
        user_msg = Message(role="user", content=text)
        if attach and screenshot:
            user_msg.images = [image_part(screenshot, media_type)]
        self.store.add_message(user_msg)
        messages = history + [user_msg]

        final_text = ""
        for _round in range(self.cfg.llm.max_tool_rounds + 1):
            turn: ChatTurn = provider.chat(
                system=system,
                messages=messages,
                tools=tools,
                on_text=self.cb.on_text_delta,
                max_tokens=self.cfg.llm.max_tokens,
            )
            assistant = Message(
                role="assistant",
                content=turn.text,
                tool_calls=turn.tool_calls,
                raw=turn.raw,
                provider=provider.name,
            )
            messages.append(assistant)
            self.store.add_message(assistant)
            final_text = turn.text
            if not turn.tool_calls:
                break
            for call in turn.tool_calls:
                self.cb.on_tool(call.name, call.arguments)
                result = run_tool(tools, call.name, call.arguments)
                tool_msg = Message(role="tool", content=result, tool_call_id=call.id)
                messages.append(tool_msg)
                self.store.add_message(tool_msg)
            self.cb.on_status("thinking")
        self.cb.on_reply_done(final_text)
        return final_text

    # ---- tool callbacks --------------------------------------------------
    def _pin(self, title: str, markdown: str, kind: str) -> None:
        self.store.save_pin(title, markdown, kind)
        self.cb.on_pin(title, markdown, kind)

    def _unpin(self) -> None:
        self.store.clear_pin()
        self.cb.on_unpin()

    def _remember(self, note: str, game: str) -> None:
        self.store.remember(note, game)
        self.cb.on_memory(note)
