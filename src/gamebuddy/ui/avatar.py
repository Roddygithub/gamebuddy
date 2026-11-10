"""Buddy's face: a vector avatar painted with QPainter, no image assets.

A rounded blob wears a headset, because GameBuddy is voice-first: the mic arm
and its waves say "talk to me" better than another chat bubble.

States: idle (breathes, blinks now and then), listening (eyes widen, waves leave
the mic with the input level), thinking (eyes glance up, three dots bounce) and
speaking (the mouth opens and closes).

Every colour comes from the active theme, so the design follows the desktop:
the body takes the theme accent, the headset the secondary colour and the eyes
the background — none of them is hard-coded.
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
        self.setObjectName("buddy-avatar")
        self._size = size
        self._state = "idle"
        self._level = 0.0
        self._phase = 0.0
        self._blink_until = 0.0
        self._next_blink = time.monotonic() + random.uniform(2.0, 5.0)
        self._colors = {"accent": "#c6f24e", "accent2": "#ff6b57", "bg": "#1b1f27", "text": "#e8e9ed"}
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
    def _blob(self, c: float, r: float, breathe: float) -> QPainterPath:
        """A rounded, slightly bottom-heavy blob rather than a plain circle."""
        k = r * 0.5523
        w, h = r * (1.0 + breathe * 0.02), r * (0.94 - breathe * 0.02)
        path = QPainterPath(QPointF(c, c - h))
        path.cubicTo(QPointF(c + k, c - h), QPointF(c + (w + k) / 2, c - k * 0.9), QPointF(c + w, c))
        path.cubicTo(QPointF(c + w, c + k * 1.05), QPointF(c + k, c + h), QPointF(c, c + h))
        path.cubicTo(QPointF(c - k, c + h), QPointF(c - w, c + k * 1.05), QPointF(c - w, c))
        path.cubicTo(QPointF(c - (w + k) / 2, c - k * 0.9), QPointF(c - k, c - h), QPointF(c, c - h))
        return path

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        s = float(self._size)
        c = s / 2
        body = QColor(self._colors["accent"])
        gear = QColor(self._colors["accent2"])
        ink = QColor(self._colors["bg"])
        shine = QColor(self._colors["text"])
        r = s * 0.33
        breathe = math.sin(self._phase / 2.0) if self._state == "idle" else 0.0
        look_up = r * 0.10 if self._state == "thinking" else 0.0

        # thinking: three dots bounce above the head
        if self._state == "thinking":
            p.setPen(Qt.NoPen)
            for i in range(3):
                lift = r * 0.16 * max(0.0, math.sin(self._phase * 2.0 - i * 0.6))
                dot = QColor(gear)
                dot.setAlphaF(0.45 + 0.55 * (1 - lift / (r * 0.16 + 1e-6)))
                p.setBrush(QBrush(dot))
                p.drawEllipse(QPointF(c + (i - 1) * r * 0.34, c - r * 1.12 - lift), s * 0.035, s * 0.035)

        # body
        grad = QRadialGradient(QPointF(c - r * 0.35, c - r * 0.45), r * 1.7)
        grad.setColorAt(0.0, body.lighter(118))
        grad.setColorAt(1.0, body.darker(112))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(self._blob(c, r, breathe))

        # headset: band over the body, two cups, and a mic arm to the mouth
        band = QPen(gear, max(1.5, s * 0.09), Qt.SolidLine, Qt.RoundCap)
        p.setPen(band)
        p.setBrush(Qt.NoBrush)
        outer = r * 1.02
        p.drawArc(QRectF(c - outer, c - outer, outer * 2, outer * 2), 22 * 16, 136 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(gear))
        for sx in (-1, 1):
            p.drawRoundedRect(
                QRectF(c + sx * r - r * 0.17, c - r * 0.20, r * 0.34, r * 0.46), r * 0.17, r * 0.17
            )
        mic_y = c + r * 0.52
        arm = QPainterPath(QPointF(c + r * 0.94, c + r * 0.18))
        arm.quadTo(QPointF(c + r * 0.95, mic_y), QPointF(c + r * 0.42, mic_y))
        p.setPen(QPen(gear, max(1.2, s * 0.05), Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(arm)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(gear))
        p.drawEllipse(QPointF(c + r * 0.40, mic_y), s * 0.045, s * 0.045)

        # listening: waves leave the mic with the input level
        if self._state == "listening":
            for i, spread in enumerate((0.46, 0.70)):
                wave = QColor(gear)
                wave.setAlphaF(0.30 + 0.5 * self._level)
                p.setPen(QPen(wave, max(1.0, s * 0.03), Qt.SolidLine, Qt.RoundCap))
                p.setBrush(Qt.NoBrush)
                rad = r * (spread + 0.10 * self._level) + s * 0.02 * i
                p.drawArc(
                    QRectF(c + r * 0.40 - rad, mic_y - rad, rad * 2, rad * 2),
                    -32 * 16,
                    64 * 16,
                )

        # eyes: dark pills with a highlight, so they read at 30 px too
        glance = r * 0.16 * math.sin(self._phase * 0.8) if self._state == "thinking" else 0.0
        eye_h = r * 0.44
        if self._blinking():
            eye_h = r * 0.08
        elif self._state == "listening":
            eye_h = r * 0.52
        eye_w = r * 0.26
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(ink))
        for sx in (-1, 1):
            p.drawRoundedRect(
                QRectF(
                    c + sx * r * 0.42 + glance - eye_w / 2,
                    c - r * 0.16 - look_up - eye_h / 2,
                    eye_w,
                    eye_h,
                ),
                eye_w / 2,
                eye_w / 2,
            )
            if eye_h > r * 0.2:
                spark = QColor(shine)
                spark.setAlphaF(0.85)
                p.setBrush(QBrush(spark))
                p.drawEllipse(
                    QPointF(c + sx * r * 0.42 + glance - eye_w * 0.12, c - r * 0.16 - look_up - eye_h * 0.22),
                    s * 0.022,
                    s * 0.022,
                )
                p.setBrush(QBrush(ink))

        # mouth
        mw = r * 0.46
        my = c + r * 0.56
        p.setBrush(QBrush(ink))
        if self._state == "speaking":
            open_h = r * (0.08 + 0.20 * abs(math.sin(self._phase * 4.5)))
            open_w = mw * 0.82
            p.drawRoundedRect(
                QRectF(c - open_w / 2, my - open_h / 2, open_w, open_h),
                open_h / 2,
                open_h / 2,
            )
        elif self._state == "thinking":
            p.drawRoundedRect(QRectF(c - mw * 0.35, my - r * 0.03, mw * 0.7, r * 0.06), r * 0.03, r * 0.03)
        else:
            path = QPainterPath(QPointF(c - mw / 2, my - r * 0.04))
            path.quadTo(QPointF(c, my + r * 0.20), QPointF(c + mw / 2, my - r * 0.04))
            p.setPen(QPen(ink, max(1.2, s * 0.045), Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        p.end()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)
