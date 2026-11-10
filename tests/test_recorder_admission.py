"""Hands-free audio is admitted one utterance at a time, never queued forever."""

from __future__ import annotations

import threading

import numpy as np

from gamebuddy.audio.recorder import HandsFreeListener


def _fire(listener: HandsFreeListener) -> None:
    """Simulate one finished utterance arriving from the audio callback."""
    listener._in_speech = True
    listener._speech_start = 0.0
    listener._last_voice = 0.0
    listener._buf = [np.zeros(8000, dtype=np.float32)]
    listener._callback(np.zeros((512, 1), dtype=np.float32), 512, None, None)


def test_a_second_utterance_is_dropped_while_one_is_in_flight():
    release = threading.Event()
    answering = threading.Event()
    seen: list[int] = []

    def on_utterance(_wav: bytes) -> None:
        seen.append(1)
        answering.set()
        release.wait(5)

    listener = HandsFreeListener(on_utterance=on_utterance)
    _fire(listener)
    assert answering.wait(5)
    _fire(listener)  # arrives while the first one is still being answered
    release.set()
    assert seen == [1]
    assert listener.dropped == 1
