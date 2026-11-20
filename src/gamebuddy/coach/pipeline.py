"""Coach mode: periodic observation → change filter → structured state → gate → stability → advice.

A passing observation is confirmed by one cheap re-capture a fraction of a second
later, so advice describes a screen that persisted rather than a transient frame —
without paying a whole interval for the check.

Off by default. Designed to stay silent unless a long-lived decision window is
clearly visible and the structured state passes every grounding check.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable

from gamebuddy.coach.gate import Observation, parse_observation, similar, validate
from gamebuddy.coach.observer import dhash, hash_distance, is_blank
from gamebuddy.config import Config
from gamebuddy.llm.base import LLMProvider, Message, image_part
from gamebuddy.memory import Store
from gamebuddy.prompts import COACH_SYSTEM

log = logging.getLogger(__name__)

# When coach.save_frames is on, keep at most this many candidate frames per game
# so the directory stays bounded even across long sessions.
MAX_SAVED_FRAMES = 200


def observe_message(frame: bytes, game_title: str = "") -> Message:
    """The single perception call used by both the live coach and the eval harness."""
    prompt = "Observe this frame and return the JSON object."
    if game_title:
        prompt = f"Game window title: {game_title}. " + prompt
    return Message(role="user", content=prompt, images=[image_part(frame, "image/jpeg")])


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
        capture_fresh: Callable[[], bytes | None] | None = None,
    ):
        self.cfg = cfg
        self.store = store
        self.provider_factory = provider_factory
        self.capture = capture
        # Confirming stability needs a new frame, never a cached one.
        self.capture_fresh = capture_fresh or capture
        self.on_advice = on_advice
        self.on_status = on_status
        self.language = language
        self.game_title = game_title
        self._provider: LLMProvider | None = None
        self._thread: threading.Thread | None = None
        self._tick_lock = threading.Lock()
        self._stop = threading.Event()
        self._last_hash: int | None = None
        self._last_saved_hash: int | None = None
        self._last_advice = ""
        self._last_advice_at = 0.0
        self._delivery_lock = threading.Lock()
        self._next_due = 0.0
        self.paused = False
        self.needs_vision = False
        self.metrics = {
            "frames": 0,
            "candidates": 0,
            "reasoner_calls": 0,
            "advised": 0,
            "rejected": 0,
            "confirm_checks": 0,
            "blank_frames": 0,
            "needs_vision": 0,
            "last_frame_bytes": 0,
            "last_turn": {},
        }

    # ---- lifecycle -------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._delivery_lock:
            if self.running and not self._stop.is_set():
                return
            stop_event = threading.Event()
            self._stop = stop_event
            self._next_due = time.monotonic() + self.cfg.coach.interval_s
            self._thread = threading.Thread(
                target=self._loop, args=(stop_event,), name="gamebuddy-coach", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        with self._delivery_lock:
            self._stop.set()

    # ---- loop ------------------------------------------------------------
    def _loop(self, stop_event: threading.Event | None = None) -> None:
        """Fixed-rate: a slow turn must not push every later look back with it."""
        stop_event = stop_event or self._stop
        while True:
            if stop_event.wait(max(0.0, self._next_due - time.monotonic())):
                return
            if stop_event.is_set():
                return
            self._next_due += self.cfg.coach.interval_s
            now = time.monotonic()
            if self._next_due <= now:  # fell behind: skip missed turns, never burst
                self._next_due = now + self.cfg.coach.interval_s
            if self.paused:
                continue
            try:
                self.tick(stop_event)
            except Exception as exc:  # noqa: BLE001
                log.warning("coach tick failed: %s", exc)
                self.store.log_coach("error", "", str(exc), self.game_title)

    def can_see(self) -> tuple[bool, str]:
        """Can the configured model look at a frame at all?

        The coach reads the whole screen — bars, ranges, shop odds, map — so it is
        vision-only by design. A text model would answer from the window title,
        which is worse than saying nothing.
        """
        if self._provider is None:
            self._provider = self.provider_factory()
        label = f"{self._provider.name}/{self._provider.model}".strip("/")
        return self._provider.supports_vision(), label

    def tick(self, stop_event: threading.Event | None = None) -> Observation | None:
        stop_event = stop_event or self._stop
        # A stopped tick may still be waiting for capture/provider I/O. Keep its
        # shared hash and provider state from racing a newly started cycle.
        with self._tick_lock:
            if stop_event.is_set():
                return None
            return self._tick(stop_event)

    def _tick(self, stop_event: threading.Event) -> Observation | None:
        ok, label = self.can_see()
        if not ok:
            if not self.needs_vision:  # say it once, not every interval
                self.needs_vision = True
                self.metrics["needs_vision"] = 1
                self.store.log_coach("pre_gate", "no_vision", label, self.game_title)
                log.warning("coach needs a vision model, %s cannot see images", label)
            return None
        started = time.monotonic()
        frame = self.capture()
        if stop_event.is_set() or not frame:
            return None
        self.metrics["frames"] += 1
        self.metrics["last_frame_bytes"] = len(frame)
        capture_ms = int((time.monotonic() - started) * 1000)
        if is_blank(frame):
            # A black or uniform frame is a capture problem, not a game state.
            self.metrics["blank_frames"] += 1
            self.store.log_coach("pre_gate", "blank_frame", "", self.game_title)
            return None
        h = dhash(frame)
        if self._last_hash is not None and hash_distance(h, self._last_hash) < self.cfg.coach.min_change:
            # Nothing moved since the last look: this screen was already judged.
            return None
        self.metrics["candidates"] += 1
        if self.cfg.coach.save_frames and self._last_saved_hash != h:
            self._save_frame(frame)
            self._last_saved_hash = h
        if time.monotonic() - self._last_advice_at < self.cfg.coach.cooldown_s:
            self.store.log_coach("pre_gate", "cooldown", "", self.game_title)
            return None

        # Mark only a frame that actually reaches the reasoner. A candidate that
        # arrives during cooldown must be retried once the cooldown expires.
        eval_started = time.monotonic()
        obs = self.evaluate(frame)
        eval_ms = int((time.monotonic() - eval_started) * 1000)
        if stop_event.is_set():
            self._log_turn(capture_ms, eval_ms, 0, "cancelled")
            return None
        self._last_hash = h
        if obs is None:
            self._log_turn(capture_ms, eval_ms, 0, "rejected")
            return None

        # Hold the advice until one cheap look confirms the screen is still similar.
        # This reduces transient advice; a perceptual hash is not a hard guarantee.
        self.store.log_coach("pre_gate", "await_stability", obs.advice, self.game_title)
        confirm_started = time.monotonic()
        stable = self._confirm(stop_event)
        confirm_ms = int((time.monotonic() - confirm_started) * 1000)
        if not stable:
            self.store.log_coach("pre_gate", "screen_moved", obs.advice, self.game_title)
            self._log_turn(capture_ms, eval_ms, confirm_ms, "dropped")
            return None
        # stop() and delivery share a lock so cancellation during confirmation
        # cannot leak advice after Coach has been disabled.
        with self._delivery_lock:
            if stop_event.is_set():
                self._log_turn(capture_ms, eval_ms, confirm_ms, "cancelled")
                return None
            self._deliver(obs)
        self._log_turn(capture_ms, eval_ms, confirm_ms, "delivered")
        return obs

    def _confirm(self, stop_event: threading.Event | None = None) -> bool:
        """Did the screen we just judged survive one more look?

        Polling at ``confirm_poll_s`` costs a capture and a perceptual hash instead
        of a full interval of silence — the frame is already in hand.
        """
        stop_event = stop_event or self._stop
        if stop_event.wait(self.cfg.coach.confirm_poll_s):
            return False
        frame = self.capture_fresh()
        self.metrics["confirm_checks"] += 1
        if stop_event.is_set() or not frame:
            return False
        h = dhash(frame)
        if self._last_hash is not None and hash_distance(h, self._last_hash) >= self.cfg.coach.min_change:
            return False
        return True

    def _log_turn(self, capture_ms: int, eval_ms: int, confirm_ms: int, outcome: str) -> None:
        self.metrics["last_turn"] = {
            "outcome": outcome,
            "capture_ms": capture_ms,
            "eval_ms": eval_ms,
            "confirm_ms": confirm_ms,
            "frame_kib": self.metrics["last_frame_bytes"] // 1024,
        }
        log.info(
            "coach turn %s: capture=%dms eval=%dms confirm=%dms frame=%dKiB",
            outcome,
            capture_ms,
            eval_ms,
            confirm_ms,
            self.metrics["last_frame_bytes"] // 1024,
        )

    def evaluate(self, frame: bytes) -> Observation | None:
        """One reasoning call. Returns the advice to deliver, or None if gated out."""
        if self._provider is None:
            self._provider = self.provider_factory()
        self.metrics["reasoner_calls"] += 1
        system = COACH_SYSTEM.replace("{language}", self.language)
        msg = observe_message(frame, self.game_title)
        turn = self._provider.chat(system=system, messages=[msg], max_tokens=900, json_mode=True)
        try:
            obs = parse_observation(turn.text)
        except (ValueError, TypeError) as exc:
            self.store.log_coach("parse", "error", f"{exc}: {turn.text[:300]}", self.game_title)
            self.metrics["rejected"] += 1
            return None
        accepted, reason = validate(obs, self.cfg.coach.min_confidence)
        if accepted and self._last_advice and similar(obs.advice, self._last_advice) > 0.6:
            accepted, reason = False, "redundant"
        self.store.log_coach(
            "gate", "accepted" if accepted else reason, obs.advice or obs.rationale, self.game_title
        )
        if not accepted:
            self.metrics["rejected"] += 1
            return None
        return obs

    def _deliver(self, obs: Observation) -> None:
        self.metrics["advised"] += 1
        self._last_advice = obs.advice
        self._last_advice_at = time.monotonic()
        self.store.log_coach("pre_gate", "delivered", obs.advice, self.game_title)
        self.on_advice(obs)

    def _save_frame(self, frame: bytes) -> None:
        """Persist candidate frames so real sessions can be annotated into eval cases."""
        from gamebuddy.paths import coach_frames_dir

        slug = re.sub(r"\W+", "-", self.game_title or "unknown").strip("-").lower()[:40] or "unknown"
        directory = coach_frames_dir() / slug
        directory.mkdir(parents=True, exist_ok=True)
        self.metrics["saved_frames"] = self.metrics.get("saved_frames", 0) + 1
        stamp = time.strftime("%Y%m%d-%H%M%S")
        (directory / f"{stamp}-{self.metrics['saved_frames']:04d}.jpg").write_bytes(frame)
        keep = sorted(directory.glob("*.jpg"))
        for old in keep[: max(0, len(keep) - MAX_SAVED_FRAMES)]:
            old.unlink(missing_ok=True)
