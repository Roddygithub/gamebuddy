"""Buddy's face: a vector avatar painted with QPainter, no image assets.

States: idle (blinks now and then), listening (ring pulses with the mic level),
thinking (eyes glance around, three orbiting dots), speaking (mouth moves).
Colors come from the active theme (Omarchy palette when enabled).
"""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget

STATES = ("idle", "listening", "thinking", "speaking")

STATUS_TO_STATE = {
    "listening": "listening",
    "hands_free_on": "listening",
    "transcribing": "thinking",
    "thinking": "thinking",
    "searching": "thinking",
    "speaking": "speaking",
}


def state_for_status(status_key: str) -> str:
    return STATUS_TO_STATE.get(status_key, "idle")


class Avatar(QWidget):
    clicked = Signal()

    def __init__(self, size: int = 32, parent: QWidget | None = None, animate: bool = True):
        super().__init__(parent)
        self._size = size
        self._state = "idle"
        self._level = 0.0
        self._phase = 0.0
        self._blink_until = 0.0
        self._next_blink = time.monotonic() + random.uniform(2.0, 5.0)
        self._colors = {"accent": "#8b5cf6", "accent2": "#22c55e", "bg": "#15171c", "text": "#e8e9ed"}
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        if animate:
            self._timer.start()

    # ---- API -----------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        if state not in STATES:
            state = "idle"
        if state != self._state:
            self._state = state
            self._phase = 0.0
            self.update()

    def set_status(self, status_key: str) -> None:
        self.set_state(state_for_status(status_key))

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level * 8))

    def set_colors(self, colors: dict[str, str]) -> None:
        self._colors.update({k: v for k, v in colors.items() if k in self._colors})
        self.update()

    def set_size(self, size: int) -> None:
        self._size = size
        self.setFixedSize(size, size)
        self.update()

    # ---- animation -----------------------------------------------------------
    def _tick(self) -> None:
        self._phase += 0.04 * 2 * math.pi  # one cycle per second
        now = time.monotonic()
        if self._state == "idle" and now >= self._next_blink:
            self._blink_until = now + 0.12
            self._next_blink = now + random.uniform(2.5, 6.0)
        self.update()

    def _blinking(self) -> bool:
        return time.monotonic() < self._blink_until

    # ---- painting ------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        s = float(self._size)
        c = s / 2
        accent = QColor(self._colors["accent"])
        accent2 = QColor(self._colors["accent2"])
        face = QColor(self._colors["text"])
        r = s * 0.40

        # outer ring: listening pulses with the mic level, thinking rotates dots
        if self._state == "listening":
            ring = QColor(accent2)
            ring.setAlphaF(0.35 + 0.45 * self._level)
            rr = r + s * (0.06 + 0.08 * self._level + 0.02 * math.sin(self._phase * 2))
            p.setPen(QPen(ring, max(1.5, s * 0.05)))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(c, c), rr, rr)
        elif self._state == "thinking":
            p.setPen(Qt.NoPen)
            for i in range(3):
                a = self._phase * 1.5 + i * 2 * math.pi / 3
                dot = QColor(accent2)
                dot.setAlphaF(0.4 + 0.6 * ((math.sin(a) + 1) / 2))
                p.setBrush(QBrush(dot))
                rad = r + s * 0.09
                p.drawEllipse(QPointF(c + rad * math.cos(a), c + rad * math.sin(a)), s * 0.045, s * 0.045)

        # head
        grad = QRadialGradient(QPointF(c - r * 0.3, c - r * 0.35), r * 1.5)
        grad.setColorAt(0.0, accent.lighter(135))
        grad.setColorAt(1.0, accent.darker(125))
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(c, c), r, r)

        # antenna
        p.setPen(QPen(face, max(1.0, s * 0.04), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(c, c - r), QPointF(c, c - r - s * 0.08))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(accent2 if self._state != "idle" else face))
        p.drawEllipse(QPointF(c, c - r - s * 0.10), s * 0.045, s * 0.045)

        # eyes
        eye_dx, eye_dy = r * 0.38, -r * 0.12
        glance = 0.0
        if self._state == "thinking":
            glance = r * 0.12 * math.sin(self._phase * 0.8)
        eye_w, eye_h = s * 0.075, s * 0.11
        if self._blinking():
            eye_h = s * 0.015
        if self._state == "listening":
            eye_h *= 1.15
        p.setBrush(QBrush(face))
        for sx in (-1, 1):
            p.drawEllipse(QPointF(c + sx * eye_dx + glance, c + eye_dy), eye_w, eye_h)

        # mouth
        pen = QPen(face, max(1.2, s * 0.05), Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        my = c + r * 0.42
        mw = r * 0.55
        if self._state == "speaking":
            open_h = r * (0.10 + 0.22 * abs(math.sin(self._phase * 4.5)))
            p.setBrush(QBrush(QColor(self._colors["bg"])))
            p.drawRoundedRect(QRectF(c - mw / 2, my - open_h / 2, mw, open_h), open_h / 2, open_h / 2)
        elif self._state == "thinking":
            p.drawLine(QPointF(c - mw * 0.35, my), QPointF(c + mw * 0.35, my))
        else:
            path = QPainterPath(QPointF(c - mw / 2, my - r * 0.05))
            path.quadTo(QPointF(c, my + r * 0.22), QPointF(c + mw / 2, my - r * 0.05))
            p.drawPath(path)
        p.end()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)
