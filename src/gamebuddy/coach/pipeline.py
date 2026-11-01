"""Coach mode: periodic observation → change filter → structured state → gate → short advice.

Off by default. Designed to stay silent unless a long-lived decision window is
clearly visible and the structured state passes every grounding check.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from gamebuddy.coach.gate import Observation, parse_observation, similar, validate
from gamebuddy.coach.observer import dhash, hash_distance
from gamebuddy.config import Config
from gamebuddy.llm.base import LLMProvider, Message, image_part
from gamebuddy.memory import Store
from gamebuddy.prompts import COACH_SYSTEM

log = logging.getLogger(__name__)


class CoachPipeline:
    def __init__(
        self,
        cfg: Config,
        store: Store,
        provider_factory: Callable[[], LLMProvider],
        capture: Callable[[], bytes | None],  # returns JPEG bytes of the game window or None
        on_advice: Callable[[Observation], None],
        on_status: Callable[[str], None] = lambda key: None,
        language: str = "en",
        game_title: str = "",
    ):
        self.cfg = cfg
        self.store = store
        self.provider_factory = provider_factory
        self.capture = capture
        self.on_advice = on_advice
        self.on_status = on_status
        self.language = language
        self.game_title = game_title
        self._provider: LLMProvider | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_hash: int | None = None
        self._last_advice = ""
        self._last_advice_at = 0.0
        self.paused = False
        self.metrics = {"frames": 0, "candidates": 0, "reasoner_calls": 0, "advised": 0, "rejected": 0}

    # ---- lifecycle -------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="gamebuddy-coach", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ---- loop ------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.wait(self.cfg.coach.interval_s):
            if self.paused:
                continue
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                log.warning("coach tick failed: %s", exc)
                self.store.log_coach("error", "", str(exc), self.game_title)

    def tick(self) -> Observation | None:
        frame = self.capture()
        if not frame:
            return None
        self.metrics["frames"] += 1
        h = dhash(frame)
        if self._last_hash is not None and hash_distance(h, self._last_hash) < self.cfg.coach.min_change:
            return None
        self._last_hash = h
        self.metrics["candidates"] += 1
        if time.time() - self._last_advice_at < self.cfg.coach.cooldown_s:
            self.store.log_coach("pre_gate", "cooldown", "", self.game_title)
            return None
        return self.evaluate(frame)

    def evaluate(self, frame: bytes) -> Observation:
        if self._provider is None:
            self._provider = self.provider_factory()
        self.metrics["reasoner_calls"] += 1
        system = COACH_SYSTEM.replace("{language}", self.language)
        prompt = "Observe this frame and return the JSON object."
        if self.game_title:
            prompt = f"Game window title: {self.game_title}. " + prompt
        msg = Message(role="user", content=prompt, images=[image_part(frame, "image/jpeg")])
        turn = self._provider.chat(system=system, messages=[msg], max_tokens=900, json_mode=True)
        try:
            obs = parse_observation(turn.text)
        except (ValueError, TypeError) as exc:
            self.store.log_coach("parse", "error", f"{exc}: {turn.text[:300]}", self.game_title)
            self.metrics["rejected"] += 1
            return Observation(decision="ABSTAIN", rationale="unparseable")
        accepted, reason = validate(obs, self.cfg.coach.min_confidence)
        if accepted and self._last_advice and similar(obs.advice, self._last_advice) > 0.6:
            accepted, reason = False, "redundant"
        self.store.log_coach(
            "gate", "accepted" if accepted else reason, obs.advice or obs.rationale, self.game_title
        )
        if not accepted:
            self.metrics["rejected"] += 1
            return obs
        self.metrics["advised"] += 1
        self._last_advice = obs.advice
        self._last_advice_at = time.time()
        self.on_advice(obs)
        return obs
