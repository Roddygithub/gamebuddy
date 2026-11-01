"""The widget itself: orb (avatar + caption) or panel (header, pinned content, transcript, input)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QRegion, QTextDocument
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

from gamebuddy.i18n import Translator
from gamebuddy.ui.avatar import Avatar

ORB_W, ORB_H = 260, 96
CAPTION_MAX = 140
CAPTION_FADE_MS = 9000


def compact_for_screen(width: int, height: int, setting: bool | str = "auto") -> bool:
    """Qt reports logical pixels, so HiDPI scaling is already accounted for."""
    return width <= 1280 or height <= 800 if setting == "auto" else bool(setting)


def fit_panel(width: int, height: int, screen_width: int, screen_height: int) -> tuple[int, int]:
    return min(width, max(1, screen_width - 32)), min(height, max(1, screen_height - 32))


def _plain(markdown: str) -> str:
    doc = QTextDocument()
    doc.setMarkdown(markdown)
    return doc.toPlainText()


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


class BuddyWidget(QWidget):
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
    mode_changed = Signal(str)  # "orb" | "panel"
    _orb_signal = Signal()

    def __init__(
        self,
        tr: Translator,
        assistant_name: str,
        ptt_key: str,
        width: int,
        height: int,
        mode: str = "orb",
        compact_orb: bool | str = "auto",
    ):
        super().__init__()
        self._compact_orb_setting = compact_orb
        self._preferred_panel_size = (width, height)
        self._screen_connected = False
        screen = self.screen().availableGeometry()
        compact_orb = compact_for_screen(screen.width(), screen.height(), compact_orb)
        self._orb_size = (64, 64) if compact_orb else (ORB_W, ORB_H)
        self._mode = "panel"
        self._panel_size = (width, height)
        self._orb_signal.connect(lambda: self.set_mode("orb"))
        self.tr = tr
        self.assistant_name = assistant_name
        self.ptt_key = ptt_key
        self._compact = False
        self._drag_pos: QPoint | None = None
        self._streaming_label: QLabel | None = None
        self._streaming_text = ""
        self._status_key = "ready"

        self.setObjectName("gamebuddy-window")
        self.setWindowTitle("GameBuddy")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(width, height)
        self.setMinimumSize(300, 160)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.root = QWidget()
        self.root.setObjectName("root")
        outer.addWidget(self.root)

        # ---- orb (avatar + last words), the in-game default ---------------
        self.orb_root = QWidget()
        self.orb_root.setObjectName("orb")
        self.orb_root.setFixedSize(*self._orb_size)
        orb_layout = QHBoxLayout(self.orb_root)
        orb_layout.setContentsMargins(*((4, 4, 4, 4) if compact_orb else (10, 8, 12, 8)))
        orb_layout.setSpacing(10)
        self.orb_avatar = Avatar(56 if compact_orb else 64)
        self.orb_avatar.setToolTip(tr("panel_mode"))
        self.orb_avatar.clicked.connect(lambda: self.set_mode("panel"))
        self.caption = QLabel("")
        self.caption.setObjectName("caption")
        self.caption.setWordWrap(True)
        self.caption.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.caption.setTextFormat(Qt.PlainText)
        orb_layout.addWidget(self.orb_avatar)
        orb_layout.addWidget(self.caption, 1)
        self.caption.setVisible(not compact_orb)
        self.orb_root.hide()
        outer.addWidget(self.orb_root)
        self._caption_timer = QTimer(self)
        self._caption_timer.setSingleShot(True)
        self._caption_timer.setInterval(CAPTION_FADE_MS)
        self._caption_timer.timeout.connect(lambda: self.caption.setText(""))
        layout = QVBoxLayout(self.root)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # ---- header ----------------------------------------------------
        header = QHBoxLayout()
        self.avatar = Avatar(30)
        self.avatar.setToolTip(tr("orb_mode"))
        self.avatar.clicked.connect(lambda: self.set_mode("orb"))
        self.dot = self.avatar  # backwards-compatible name
        self.title = QLabel(assistant_name)
        self.title.setObjectName("title")
        self.title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.status = QLabel(tr("ready"))
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status.setObjectName("status")
        header.addWidget(self.dot)
        header.addWidget(self.title)
        header.addWidget(self.status, 1)

        self.btn_window = self._tool("🎯", tr("pick_window"), self.pick_window.emit)
        self.btn_ear = self._tool("👂", tr("hands_free_on"), self.toggle_hands_free.emit, checkable=True)
        self.btn_coach = self._tool("🧠", tr("coach_on"), self.toggle_coach.emit, checkable=True)
        self.btn_compact = self._tool("▾", tr("compact"), self.toggle_compact)
        self.btn_menu = self._tool("⋯", tr("settings"), self._show_menu)
        for b in (
            self.btn_window,
            self.btn_ear,
            self.btn_coach,
            self.btn_compact,
            self.btn_menu,
        ):
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
        if mode == "orb":
            self.set_mode("orb")
        for screen in QGuiApplication.screens():
            self._watch_screen(screen)
        QGuiApplication.instance().screenAdded.connect(self._watch_screen)
        self._adapt_to_screen()

    def _watch_screen(self, screen) -> None:
        screen.availableGeometryChanged.connect(self._adapt_to_screen)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._screen_connected and self.windowHandle():
            self.windowHandle().screenChanged.connect(self._adapt_to_screen)
            self._screen_connected = True
        self._adapt_to_screen()

    def _adapt_to_screen(self, *_args) -> None:
        screen = self.screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        compact = compact_for_screen(area.width(), area.height(), self._compact_orb_setting)
        self._orb_size = (64, 64) if compact else (ORB_W, ORB_H)
        self.orb_root.setFixedSize(*self._orb_size)
        self.orb_root.setStyleSheet("background: transparent; border: none;" if compact else "")
        self.orb_root.layout().setContentsMargins(*((4, 4, 4, 4) if compact else (10, 8, 12, 8)))
        self.orb_avatar.set_size(56 if compact else 64)
        self.caption.setVisible(not compact)
        self._panel_size = fit_panel(*self._preferred_panel_size, area.width(), area.height())
        if self._mode == "orb":
            self.setMinimumSize(*self._orb_size)
            self.resize(*self._orb_size)
            self.setMask(QRegion(0, 0, *self._orb_size))
        else:
            self.setMinimumSize(min(300, self._panel_size[0]), min(160, self._panel_size[1]))
            self.resize(*self._panel_size)
        if self.isVisible():
            self.move(
                max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                max(area.top(), min(self.y(), area.bottom() - self.height() + 1)),
            )

    # ---- orb / panel ---------------------------------------------------------
    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        mode = "orb" if mode == "orb" else "panel"
        if mode == self._mode:
            return
        self._mode = mode
        top_right = self.frameGeometry().topRight()
        if mode == "orb":
            self._panel_size = (self.width(), self.height())
            self.root.hide()
            self.orb_root.show()
            self.setMinimumSize(*self._orb_size)
            self.resize(*self._orb_size)
            self.setMask(QRegion(0, 0, *self._orb_size))  # clicks outside the orb reach the game
        else:
            self.orb_root.hide()
            self.root.show()
            self.clearMask()
            self.setMinimumSize(300, 160)
            self.resize(*self._panel_size)
            self.caption.setText("")
        if self.isVisible():  # keep the right edge where it was
            self.move(max(0, top_right.x() - self.width()), self.frameGeometry().top())
        self._adapt_to_screen()
        self.mode_changed.emit(mode)

    def set_caption(self, text: str, fade: bool = True) -> None:
        text = " ".join(text.split())
        if len(text) > CAPTION_MAX:
            text = text[: CAPTION_MAX - 1].rstrip() + "…"
        self.caption.setText(text)
        self._caption_timer.stop()
        if fade and text:
            self._caption_timer.start()

    def set_theme_colors(self, colors: dict[str, str]) -> None:
        self.avatar.set_colors(colors)
        self.orb_avatar.set_colors(colors)

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
            (self.tr("orb_mode"), self._orb_signal),
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
        self.status.setStyleSheet(f"color: {color};" if key != "ready" else "")
        self.avatar.set_status(key)
        self.orb_avatar.set_status(key)
        if self._mode == "orb" and key in ("listening", "transcribing", "thinking", "searching"):
            self.set_caption(self.tr(key), fade=False)

    def set_window_title(self, title: str | None) -> None:
        self.hint.setText(
            self.tr("window_selected", title=title)
            if title
            else self.tr("hold_hint", key=self.ptt_key.replace(", ", "+"))
        )

    def set_level(self, value: float) -> None:
        self.level.setValue(int(min(1.0, value * 8) * 100))
        self.avatar.set_level(value)
        self.orb_avatar.set_level(value)

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
        self.pin_body.document().setTextWidth(self.pin_body.viewport().width() or self.width() - 60)
        self.pin_body.setFixedHeight(int(min(220, self.pin_body.document().size().height() + 12)))
        self.pin_body.setVisible(True)
        self.btn_pin_toggle.setText("▾")
        if self._mode == "orb":
            self.set_mode("panel")  # pinned content is meant to stay visible next to the game
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
        if self._mode == "orb" and kind != "user":
            self.set_caption(_plain(text))
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
        if self._mode == "orb":
            self.set_caption(_plain(self._streaming_text), fade=False)

    def end_stream(self, final_text: str) -> None:
        if self._streaming_label is not None:
            if final_text.strip():
                self._streaming_label.setText(md_to_html(final_text))
            elif not self._streaming_text.strip():
                self._streaming_label.deleteLater()
        self._streaming_label = None
        self._streaming_text = ""
        self._scroll_bottom()
        if self._mode == "orb" and final_text.strip():
            self.set_caption(_plain(final_text))

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
        if event.button() == Qt.LeftButton and (event.position().y() < 48 or self._mode == "orb"):
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
