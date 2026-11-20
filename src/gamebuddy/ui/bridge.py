"""Qt signals used to hop from worker threads to the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class Bridge(QObject):
    status = Signal(str)  # i18n key
    user_text = Signal(str)
    stream_started = Signal()
    text_delta = Signal(str)
    reply_done = Signal(str)
    pin = Signal(str, str, str)
    unpin = Signal()
    memory = Signal(str)
    error = Signal(str)
    level = Signal(float)
    coach_advice = Signal(str, str, int, int)  # advice, rationale, coach and capture generations
    command = Signal(dict)  # IPC request to execute on the GUI thread
    window_lost = Signal(str, str, str, int)  # window identity and selection generation
    tool = Signal(str)
    update_available = Signal(dict)
