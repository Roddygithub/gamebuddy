"""Application wiring: widget + Kin + audio + capture + coach + IPC + tray."""

from __future__ import annotations

import logging
import threading
from typing import Any

from PySide6.QtCore import QObject, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from gamebro import APP_ID
from gamebro.capture import CaptureBackend, CaptureError, Rect, WindowInfo, get_backend, to_jpeg
from gamebro.capture.base import overlay_mask
from gamebro.coach import CoachPipeline
from gamebro.coach.gate import Observation
from gamebro.config import Config, load_config, save_config
from gamebro.i18n import Translator
from gamebro.ipc import IPCServer
from gamebro.kin import Kin, KinCallbacks
from gamebro.llm import make_provider
from gamebro.llm.router import ProviderError, coach_model
from gamebro.memory import Store
from gamebro.ui.bridge import Bridge
from gamebro.ui.theme import DEFAULT, omarchy_colors, stylesheet
from gamebro.ui.widget import BroWidget

log = logging.getLogger(__name__)


class GameBroApp(QObject):
    def __init__(self, cfg: Config | None = None):
        super().__init__()
        self.cfg = cfg or load_config()
        self.tr = Translator(self.cfg.general.language)
        self.store = Store()
        self.bridge = Bridge()
        self.pool = QThreadPool.globalInstance()
        self.backend: CaptureBackend = get_backend(self.cfg.capture.backend)
        self.window: WindowInfo | None = None
        self.recorder = None
        self.listener = None
        self.coach: CoachPipeline | None = None
        self.ipc: IPCServer | None = None
        self.tray: QSystemTrayIcon | None = None
        self._speaking = threading.Event()
        self._last_stt_text = ""

        self.kin = Kin(self.cfg, self.store, self._kin_callbacks())
        self.kin.language = self.tr.language

        self.widget = BroWidget(
            self.tr,
            self.cfg.general.assistant_name,
            self.cfg.hotkeys.push_to_talk,
            self.cfg.ui.width,
            self.cfg.ui.height,
        )
        self._apply_theme()
        self._apply_window_flags()
        self._connect()

    # ---- setup ---------------------------------------------------------------
    def _apply_theme(self) -> None:
        colors = omarchy_colors() if self.cfg.ui.theme == "omarchy" else DEFAULT
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet(colors, self.cfg.ui.font_size, self.cfg.ui.opacity))

    def _apply_window_flags(self) -> None:
        flags = Qt.FramelessWindowHint | Qt.Window
        if self.cfg.ui.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.widget.setWindowFlags(flags)

    def _connect(self) -> None:
        w, b = self.widget, self.bridge
        w.send_text.connect(self.ask_text)
        w.ptt_pressed.connect(self.ptt_start)
        w.ptt_released.connect(self.ptt_stop)
        w.toggle_hands_free.connect(self.toggle_hands_free)
        w.toggle_coach.connect(self.toggle_coach)
        w.pick_window.connect(self.pick_window)
        w.open_settings.connect(self.open_settings)
        w.unpin_requested.connect(self.unpin)
        w.quit_requested.connect(self.quit)
        w.hide_requested.connect(w.hide)
        w.new_conversation.connect(self.new_conversation)

        b.status.connect(w.set_status)
        b.user_text.connect(w.add_user)
        b.text_delta.connect(w.stream_delta)
        b.reply_done.connect(self._on_reply_done)
        b.pin.connect(w.show_pin)
        b.unpin.connect(w.clear_pin)
        b.error.connect(self._on_error)
        b.level.connect(w.set_level)
        b.coach_advice.connect(w.add_coach)
        b.command.connect(self._handle_command_gui)
        b.window_lost.connect(self._on_window_lost)
        b.memory.connect(lambda _n: w.set_status("ready"))

    def _kin_callbacks(self) -> KinCallbacks:
        b = self.bridge
        return KinCallbacks(
            on_status=b.status.emit,
            on_text_delta=b.text_delta.emit,
            on_reply_done=b.reply_done.emit,
            on_pin=b.pin.emit,
            on_unpin=b.unpin.emit,
            on_memory=b.memory.emit,
            on_error=b.error.emit,
            on_tool=lambda name, _args: b.tool.emit(name),
        )

    # ---- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        self.ipc = IPCServer(self._handle_command_threadsafe)
        try:
            self.ipc.start()
        except RuntimeError as exc:
            log.error("%s", exc)
            raise
        pin = self.store.load_pin()
        if pin:
            self.widget.show_pin(pin["title"], pin["markdown"], pin["kind"])
        for m in self.store.recent_messages(12):
            if m.role == "user" and m.content:
                self.widget.add_user(m.content)
            elif m.role == "assistant" and m.content:
                self.widget.add_bubble(m.content, "bro")
        if not self.store.recent_messages(1):
            self.widget.add_bubble(self.tr("welcome", name=self.cfg.general.assistant_name), "bro")
        self._setup_tray()
        if not self.cfg.ui.start_hidden:
            self.widget.show()
        if not self.cfg.general.onboarding_done:
            QTimer.singleShot(300, self.run_onboarding)
        if self.cfg.coach.enabled:
            QTimer.singleShot(1000, lambda: self.set_coach(True))

    def quit(self) -> None:
        self.set_hands_free(False)
        self.set_coach(False)
        if self.ipc:
            self.ipc.stop()
        save_config(self.cfg)
        self.store.close()
        app = QApplication.instance()
        if app:
            app.quit()

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = QIcon.fromTheme("audio-input-microphone", QIcon.fromTheme("applications-games"))
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        for label, slot in (
            (self.tr("show"), self.toggle_visible),
            (self.tr("hands_free_on"), self.toggle_hands_free),
            (self.tr("coach_on"), self.toggle_coach),
            (self.tr("settings"), self.open_settings),
            (self.tr("quit"), self.quit),
        ):
            act = QAction(label, menu)
            act.triggered.connect(slot)
            menu.addAction(act)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.toggle_visible() if reason == QSystemTrayIcon.Trigger else None
        )
        self.tray.setToolTip("GameBro")
        self.tray.show()

    # ---- window selection ----------------------------------------------------
    def pick_window(self) -> None:
        from gamebro.ui.picker import WindowPicker

        dlg = WindowPicker(self.backend, self.tr, APP_ID, self.widget)
        if dlg.exec() and dlg.selected:
            self.select_window(dlg.selected)

    def select_window(self, window: WindowInfo | None) -> None:
        self.window = window
        self.kin.game_title = window.title if window else ""
        if self.coach:
            self.coach.game_title = self.kin.game_title
        self.widget.set_window_title(window.title if window else None)
        if self.ipc:
            self.ipc.broadcast("window", title=self.kin.game_title, id=window.id if window else "")

    def select_window_by_id(self, window_id: str) -> bool:
        w = self.backend.find_window(window_id)
        if w:
            self.select_window(w)
        return w is not None

    def _overlay_rect(self) -> Rect | None:
        if not self.cfg.capture.mask_overlay:
            return None
        try:
            own = self.backend.own_windows(APP_ID)
        except Exception:  # noqa: BLE001
            own = []
        if own:
            return own[0].rect
        g = self.widget.frameGeometry()
        return Rect(g.x(), g.y(), g.width(), g.height()) if self.widget.isVisible() else None

    def capture_game(self) -> bytes | None:
        """JPEG of the selected game window, or None. Safe to call from worker threads."""
        if self.window is None:
            return None
        try:
            png = self.backend.capture(self.window)
        except CaptureError as exc:
            if str(exc) == "window_lost":
                self.bridge.window_lost.emit()
            else:
                log.warning("capture failed: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("capture failed: %s", exc)
            return None
        mask = overlay_mask(self.window, self._overlay_rect())
        return to_jpeg(png, self.cfg.capture.max_width, self.cfg.capture.jpeg_quality, mask)

    def _on_window_lost(self) -> None:
        self.window = None
        self.kin.game_title = ""
        self.widget.set_window_title(None)
        self.widget.add_error(self.tr("window_lost"))

    # ---- asking ------------------------------------------------------------
    def ask_text(self, text: str) -> None:
        text = text.strip()
        if not text or self.kin.busy:
            return
        self.widget.add_user(text)
        self.widget.begin_stream()
        self.pool.start(lambda: self._ask_worker(text))

    def _ask_worker(self, text: str) -> None:
        try:
            shot = self.capture_game()
            self.kin.ask(text, shot)
        except ProviderError as exc:
            key = "error_no_key" if "missing_api_key" in str(exc) else "error_generic"
            self.bridge.error.emit(self.tr(key, error=str(exc)))
        except Exception as exc:  # noqa: BLE001
            self.bridge.error.emit(self.tr("error_generic", error=str(exc)))

    def _on_reply_done(self, text: str) -> None:
        self.widget.end_stream(text)
        if text.strip() and self.cfg.speech.speak_replies and self.cfg.speech.tts != "none":
            self.pool.start(lambda: self._speak(text))

    def _speak(self, text: str) -> None:
        from gamebro.audio import player
        from gamebro.speech.tts import synthesize

        try:
            audio, fmt = synthesize(text, self.cfg, self.tr.language)
            if not audio:
                return
            self._speaking.set()
            if self.listener:
                self.listener.paused = True
            self.bridge.status.emit("speaking")
            player.play(audio, fmt, self.cfg.audio.output_device)
        except Exception as exc:  # noqa: BLE001
            log.warning("tts failed: %s", exc)
        finally:
            self._speaking.clear()
            if self.listener:
                self.listener.paused = False
            self.bridge.status.emit("ready")

    def _on_error(self, message: str) -> None:
        self.widget.end_stream("")
        self.widget.add_error(message)
        self.widget.set_status("ready")

    # ---- voice: push-to-talk -------------------------------------------------
    def ptt_start(self) -> None:
        if self.recorder and self.recorder.recording:
            return
        try:
            from gamebro.audio.recorder import Recorder

            if self.recorder is None:
                self.recorder = Recorder(
                    self.cfg.audio.sample_rate, self.cfg.audio.input_device, on_level=self.bridge.level.emit
                )
            from gamebro.audio import player

            player.stop()
            self.recorder.start()
            self.widget.set_recording(True)
            self.widget.set_status("listening")
            if self.ipc:
                self.ipc.broadcast("status", key="listening")
        except Exception as exc:  # noqa: BLE001
            self.widget.add_error(self.tr("error_mic", error=str(exc)))

    def ptt_stop(self) -> None:
        if not self.recorder or not self.recorder.recording:
            return
        wav = self.recorder.stop()
        self.widget.set_recording(False)
        if not wav:
            self.widget.set_status("ready")
            return
        self.widget.set_status("transcribing")
        self.pool.start(lambda: self._transcribe_and_ask(wav))

    def ptt_toggle(self) -> None:
        if self.recorder and self.recorder.recording:
            self.ptt_stop()
        else:
            self.ptt_start()

    def _transcribe_and_ask(self, wav: bytes) -> None:
        from gamebro.speech.stt import transcribe

        try:
            text = transcribe(wav, self.cfg)
        except Exception as exc:  # noqa: BLE001
            self.bridge.error.emit(self.tr("error_stt", error=str(exc)))
            return
        if not text.strip():
            self.bridge.status.emit("ready")
            return
        self.bridge.user_text.emit(text)
        QTimer.singleShot(0, self.widget.begin_stream)
        shot = self.capture_game()
        try:
            self.kin.ask(text, shot)
        except ProviderError as exc:
            key = "error_no_key" if "missing_api_key" in str(exc) else "error_generic"
            self.bridge.error.emit(self.tr(key, error=str(exc)))

    # ---- voice: hands-free ---------------------------------------------------
    def toggle_hands_free(self) -> None:
        self.set_hands_free(not (self.listener and self.listener.active))

    def set_hands_free(self, on: bool) -> None:
        if on:
            try:
                from gamebro.audio.recorder import HandsFreeListener

                if self.listener is None:
                    a = self.cfg.audio
                    self.listener = HandsFreeListener(
                        on_utterance=self._transcribe_and_ask,
                        sample_rate=a.sample_rate,
                        device=a.input_device,
                        threshold=a.vad_threshold,
                        silence_ms=a.vad_silence_ms,
                        max_utterance_s=a.vad_max_utterance_s,
                        idle_sleep_s=a.listening_idle_sleep_s,
                        on_level=self.bridge.level.emit,
                        on_sleep=lambda: self.bridge.command.emit({"cmd": "listen", "action": "off"}),
                    )
                self.listener.start()
            except Exception as exc:  # noqa: BLE001
                self.widget.add_error(self.tr("error_mic", error=str(exc)))
                return
        elif self.listener:
            self.listener.stop()
        self.widget.set_hands_free(on)
        self.widget.set_status("hands_free_on" if on else "ready")
        QTimer.singleShot(1500, lambda: self.widget.set_status("ready") if on else None)

    # ---- coach ---------------------------------------------------------------
    def toggle_coach(self) -> None:
        self.set_coach(not (self.coach and self.coach.running))

    def set_coach(self, on: bool) -> None:
        if on:
            if self.coach is None:
                self.coach = CoachPipeline(
                    cfg=self.cfg,
                    store=self.store,
                    provider_factory=lambda: make_provider(self.cfg, coach_model(self.cfg)),
                    capture=self.capture_game,
                    on_advice=self._on_coach_advice,
                    language=self.tr.language,
                    game_title=self.kin.game_title,
                )
            self.coach.start()
        elif self.coach:
            self.coach.stop()
        self.widget.set_coach(on)
        self.widget.set_status("coach_on" if on else "coach_off")
        QTimer.singleShot(1500, lambda: self.widget.set_status("ready"))

    def _on_coach_advice(self, obs: Observation) -> None:
        self.bridge.coach_advice.emit(obs.advice, obs.rationale)
        if self.ipc:
            self.ipc.broadcast("coach", advice=obs.advice)
        if self.cfg.coach.speak:
            self.pool.start(lambda: self._speak(obs.advice))

    # ---- misc ----------------------------------------------------------------
    def unpin(self) -> None:
        self.store.clear_pin()
        self.widget.clear_pin()

    def new_conversation(self) -> None:
        self.store.new_conversation(self.kin.game_title)
        self.widget.clear_feed()

    def toggle_visible(self) -> None:
        if self.widget.isVisible():
            self.widget.hide()
        else:
            self.widget.show()
            self.widget.raise_()
            self.widget.activateWindow()

    def open_settings(self) -> None:
        from gamebro.ui.settings import SettingsDialog

        dlg = SettingsDialog(self.cfg, self.tr, self.widget)
        if dlg.exec():
            self.tr.set_language(self.cfg.general.language)
            self.kin.language = self.tr.language
            self.kin.reset_provider()
            if self.coach:
                self.coach._provider = None
            self.listener = None
            self._apply_theme()
            self.widget.title.setText(self.cfg.general.assistant_name)
            self.widget.set_window_title(self.window.title if self.window else None)

    def run_onboarding(self) -> None:
        from gamebro.ui.onboarding import OnboardingWizard

        wiz = OnboardingWizard(self.cfg, self.tr, self.backend, self.widget)
        if wiz.exec():
            self.tr.set_language(self.cfg.general.language)
            self.kin.language = self.tr.language
            self.kin.reset_provider()
            self.widget.title.setText(self.cfg.general.assistant_name)
            if wiz.selected_window:
                self.select_window(wiz.selected_window)

    # ---- IPC -----------------------------------------------------------------
    def status_snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "visible": self.widget.isVisible(),
            "window": self.kin.game_title,
            "window_id": self.window.id if self.window else "",
            "recording": bool(self.recorder and self.recorder.recording),
            "hands_free": bool(self.listener and self.listener.active),
            "coach": bool(self.coach and self.coach.running),
            "busy": self.kin.busy,
            "backend": self.backend.name,
            "language": self.tr.language,
        }

    def _handle_command_threadsafe(self, req: dict[str, Any]) -> dict[str, Any]:
        cmd = req.get("cmd")
        if cmd == "ping":
            return {"ok": True, "app": "gamebro"}
        if cmd == "status":
            return self.status_snapshot()
        if cmd == "windows":
            try:
                return {
                    "ok": True,
                    "windows": [w.__dict__ | {"rect": w.rect.__dict__} for w in self.backend.list_windows()],
                }
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": str(exc)}
        self.bridge.command.emit(req)
        return {"ok": True, "queued": cmd}

    def _handle_command_gui(self, req: dict[str, Any]) -> None:
        cmd, action = req.get("cmd"), req.get("action", "toggle")
        if cmd == "ptt":
            {"start": self.ptt_start, "stop": self.ptt_stop, "toggle": self.ptt_toggle}.get(
                action, self.ptt_toggle
            )()
        elif cmd == "ask":
            self.ask_text(str(req.get("text", "")))
        elif cmd == "toggle":
            self.toggle_visible()
        elif cmd == "show":
            self.widget.show()
            self.widget.raise_()
        elif cmd == "hide":
            self.widget.hide()
        elif cmd == "listen":
            self.set_hands_free(
                action == "on" if action in ("on", "off") else not (self.listener and self.listener.active)
            )
        elif cmd == "coach":
            self.set_coach(
                action == "on" if action in ("on", "off") else not (self.coach and self.coach.running)
            )
        elif cmd == "select_window":
            if not self.select_window_by_id(str(req.get("id", ""))):
                self.pick_window()
        elif cmd == "pick_window":
            self.pick_window()
        elif cmd == "unpin":
            self.unpin()
        elif cmd == "settings":
            self.open_settings()
        elif cmd == "quit":
            self.quit()


def run_app(argv: list[str] | None = None) -> int:
    import sys

    QGuiApplication.setDesktopFileName(APP_ID)
    app = QApplication(argv or sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName("GameBro")
    app.setQuitOnLastWindowClosed(False)
    gb = GameBroApp()
    try:
        gb.start()
    except RuntimeError as exc:
        print(f"gamebro: {exc}", file=sys.stderr)
        return 2
    return app.exec()
