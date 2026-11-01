"""The widget itself: header, pinned panel, transcript, input."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QTextDocument
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gamebro.i18n import Translator


def md_to_html(markdown: str) -> str:
    doc = QTextDocument()
    doc.setMarkdown(markdown)
    return doc.toHtml()


class MicButton(QToolButton):
    """Hold to talk; a short click toggles hands-free listening."""

    hold_started = Signal()
    hold_finished = Signal()
    clicked_short = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("mic")
        self.setText("🎤")
        self.setFixedSize(36, 36)
        self.setCursor(Qt.PointingHandCursor)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._start_hold)
        self._holding = False

    def _start_hold(self) -> None:
        self._holding = True
        self.hold_started.emit()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._holding = False
            self._timer.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            if self._timer.isActive():
                self._timer.stop()
                self.clicked_short.emit()
            elif self._holding:
                self._holding = False
                self.hold_finished.emit()
        super().mouseReleaseEvent(event)


class BroWidget(QWidget):
    send_text = Signal(str)
    ptt_pressed = Signal()
    ptt_released = Signal()
    toggle_hands_free = Signal()
    toggle_coach = Signal()
    pick_window = Signal()
    open_settings = Signal()
    unpin_requested = Signal()
    quit_requested = Signal()
    hide_requested = Signal()
    new_conversation = Signal()

    def __init__(self, tr: Translator, assistant_name: str, ptt_key: str, width: int, height: int):
        super().__init__()
        self.tr = tr
        self.assistant_name = assistant_name
        self.ptt_key = ptt_key
        self._compact = False
        self._drag_pos: QPoint | None = None
        self._streaming_label: QLabel | None = None
        self._streaming_text = ""
        self._status_key = "ready"

        self.setObjectName("gamebro-window")
        self.setWindowTitle("GameBro")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(width, height)
        self.setMinimumSize(300, 160)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.root = QWidget()
        self.root.setObjectName("root")
        outer.addWidget(self.root)
        layout = QVBoxLayout(self.root)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # ---- header ----------------------------------------------------
        header = QHBoxLayout()
        self.dot = QLabel("●")
        self.dot.setObjectName("dot")
        self.title = QLabel(assistant_name)
        self.title.setObjectName("title")
        self.status = QLabel(tr("ready"))
        self.status.setObjectName("status")
        header.addWidget(self.dot)
        header.addWidget(self.title)
        header.addWidget(self.status, 1)

        self.btn_window = self._tool("🎯", tr("pick_window"), self.pick_window.emit)
        self.btn_ear = self._tool("👂", tr("hands_free_on"), self.toggle_hands_free.emit, checkable=True)
        self.btn_coach = self._tool("🧠", tr("coach_on"), self.toggle_coach.emit, checkable=True)
        self.btn_compact = self._tool("▾", tr("compact"), self.toggle_compact)
        self.btn_menu = self._tool("⋯", tr("settings"), self._show_menu)
        for b in (self.btn_window, self.btn_ear, self.btn_coach, self.btn_compact, self.btn_menu):
            header.addWidget(b)
        layout.addLayout(header)

        self.hint = QLabel(tr("hold_hint", key=ptt_key.replace(", ", "+")))
        self.hint.setObjectName("hint")
        layout.addWidget(self.hint)

        # ---- pinned ----------------------------------------------------
        self.pin_frame = QFrame()
        self.pin_frame.setObjectName("pin")
        pin_layout = QVBoxLayout(self.pin_frame)
        pin_layout.setContentsMargins(10, 8, 10, 8)
        pin_head = QHBoxLayout()
        self.pin_title = QLabel("")
        self.pin_title.setObjectName("title")
        pin_head.addWidget(QLabel("📌"))
        pin_head.addWidget(self.pin_title, 1)
        self.btn_pin_toggle = self._tool("▾", "", self._toggle_pin_body)
        pin_head.addWidget(self.btn_pin_toggle)
        pin_head.addWidget(self._tool("✕", tr("unpin"), self.unpin_requested.emit))
        pin_layout.addLayout(pin_head)
        self.pin_body = QTextBrowser()
        self.pin_body.setOpenExternalLinks(True)
        self.pin_body.setMaximumHeight(220)
        pin_layout.addWidget(self.pin_body)
        self.pin_frame.hide()
        layout.addWidget(self.pin_frame)

        # ---- transcript ------------------------------------------------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.feed = QWidget()
        self.feed_layout = QVBoxLayout(self.feed)
        self.feed_layout.setContentsMargins(0, 0, 4, 0)
        self.feed_layout.setSpacing(6)
        self.feed_layout.addStretch(1)
        self.scroll.setWidget(self.feed)
        layout.addWidget(self.scroll, 1)

        # ---- input -----------------------------------------------------
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setValue(0)
        self.level.setTextVisible(False)
        self.level.setFixedHeight(4)
        layout.addWidget(self.level)

        row = QHBoxLayout()
        self.mic = MicButton()
        self.mic.hold_started.connect(self.ptt_pressed.emit)
        self.mic.hold_finished.connect(self.ptt_released.emit)
        self.mic.clicked_short.connect(self.toggle_hands_free.emit)
        self.input = QLineEdit()
        self.input.setPlaceholderText(tr("type_placeholder", name=assistant_name))
        self.input.returnPressed.connect(self._submit)
        self.btn_send = self._tool("➤", tr("send"), self._submit)
        row.addWidget(self.mic)
        row.addWidget(self.input, 1)
        row.addWidget(self.btn_send)
        layout.addLayout(row)

        self._body_widgets = [self.hint, self.pin_frame, self.scroll, self.level]
        self._input_row = row

    # ---- helpers -----------------------------------------------------------
    def _tool(self, text: str, tip: str, slot: Callable[[], None], checkable: bool = False) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setCursor(Qt.PointingHandCursor)
        if checkable:
            b.clicked.connect(lambda _checked=False: slot())
        else:
            b.clicked.connect(slot)
        return b

    def _show_menu(self) -> None:
        menu = QMenu(self)
        for label, sig in (
            (self.tr("settings"), self.open_settings),
            (self.tr("pick_window"), self.pick_window),
            ("—", None),
            (self.tr("notes") + " ↺", self.new_conversation),
            (self.tr("hide"), self.hide_requested),
            (self.tr("quit"), self.quit_requested),
        ):
            if sig is None:
                menu.addSeparator()
                continue
            act = QAction(label, self)
            act.triggered.connect(sig.emit)
            menu.addAction(act)
        menu.exec(self.btn_menu.mapToGlobal(QPoint(0, self.btn_menu.height())))

    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.send_text.emit(text)

    def _toggle_pin_body(self) -> None:
        visible = not self.pin_body.isVisible()
        self.pin_body.setVisible(visible)
        self.btn_pin_toggle.setText("▾" if visible else "▸")

    def toggle_compact(self) -> None:
        self._compact = not self._compact
        for w in self._body_widgets:
            w.setVisible(not self._compact and (w is not self.pin_frame or bool(self.pin_title.text())))
        self.input.setVisible(not self._compact)
        self.btn_send.setVisible(not self._compact)
        self.btn_compact.setText("▸" if self._compact else "▾")
        if self._compact:
            self._expanded_size = self.size()
            self.resize(self.width(), 96)
        else:
            self.resize(getattr(self, "_expanded_size", self.size()))

    # ---- public API (GUI thread) --------------------------------------------
    def set_status(self, key: str) -> None:
        self._status_key = key
        self.status.setText(self.tr(key))
        color = {
            "listening": "#ef4444",
            "thinking": "#f59e0b",
            "speaking": "#8b5cf6",
            "searching": "#f59e0b",
        }.get(key, "#22c55e")
        self.dot.setStyleSheet(f"color: {color}; font-size: 17px;")

    def set_window_title(self, title: str | None) -> None:
        self.hint.setText(
            self.tr("window_selected", title=title)
            if title
            else self.tr("hold_hint", key=self.ptt_key.replace(", ", "+"))
        )

    def set_level(self, value: float) -> None:
        self.level.setValue(int(min(1.0, value * 8) * 100))

    def set_hands_free(self, on: bool) -> None:
        self.btn_ear.setChecked(on)
        self.btn_ear.setToolTip(self.tr("hands_free_off" if on else "hands_free_on"))

    def set_coach(self, on: bool) -> None:
        self.btn_coach.setChecked(on)
        self.btn_coach.setToolTip(self.tr("coach_off" if on else "coach_on"))

    def set_recording(self, on: bool) -> None:
        self.mic.setDown(on)
        if not on:
            self.level.setValue(0)

    def show_pin(self, title: str, markdown: str, kind: str = "note") -> None:
        icon = {"build": "🛠", "checklist": "☑", "table": "▦", "link": "🔗", "video": "▶"}.get(kind, "📌")
        self.pin_title.setText(f"{icon} {title}")
        self.pin_body.setMarkdown(markdown)
        self.pin_body.setVisible(True)
        self.btn_pin_toggle.setText("▾")
        if not self._compact:
            self.pin_frame.show()

    def clear_pin(self) -> None:
        self.pin_title.setText("")
        self.pin_body.clear()
        self.pin_frame.hide()

    def add_bubble(self, text: str, kind: str = "bro") -> QLabel:
        label = QLabel()
        label.setObjectName(f"bubble_{kind}")
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        label.setText(md_to_html(text) if kind != "user" else text)
        self.feed_layout.insertWidget(self.feed_layout.count() - 1, label)
        QTimer.singleShot(0, self._scroll_bottom)
        return label

    def add_user(self, text: str) -> None:
        self.add_bubble(text, "user")

    def add_coach(self, advice: str, rationale: str = "") -> None:
        body = f"**{self.tr('coach_advice')}** — {advice}"
        if rationale:
            body += f"\n\n<small>{rationale}</small>"
        self.add_bubble(body, "coach")

    def add_error(self, text: str) -> None:
        self.add_bubble(text, "error")

    def begin_stream(self) -> None:
        self._streaming_text = ""
        self._streaming_label = self.add_bubble("…", "bro")

    def stream_delta(self, delta: str) -> None:
        if self._streaming_label is None:
            self.begin_stream()
        self._streaming_text += delta
        assert self._streaming_label is not None
        self._streaming_label.setText(md_to_html(self._streaming_text))
        self._scroll_bottom()

    def end_stream(self, final_text: str) -> None:
        if self._streaming_label is not None:
            if final_text.strip():
                self._streaming_label.setText(md_to_html(final_text))
            elif not self._streaming_text.strip():
                self._streaming_label.deleteLater()
        self._streaming_label = None
        self._streaming_text = ""
        self._scroll_bottom()

    def clear_feed(self) -> None:
        while self.feed_layout.count() > 1:
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _scroll_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---- window move -------------------------------------------------------
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and event.position().y() < 48:
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                return
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.hide_requested.emit()
        super().keyPressEvent(event)
