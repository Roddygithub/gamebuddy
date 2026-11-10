"""Application wiring: widget + Kin + audio + capture + coach + IPC + tray."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from importlib.resources import files
from pathlib import Path
from typing import Any

from PySide6.QtCore import QFileSystemWatcher, QObject, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from gamebuddy import APP_ID
from gamebuddy.capture import (
    CaptureBackend,
    CaptureError,
    Rect,
    WindowInfo,
    find_same_window,
    get_backend,
    load_remembered_window,
    remember_window,
    to_jpeg,
)
from gamebuddy.capture.base import overlay_mask
from gamebuddy.coach import CoachPipeline
from gamebuddy.coach.gate import Observation
from gamebuddy.config import Config, load_config, save_config
from gamebuddy.i18n import Translator, is_rtl
from gamebuddy.ipc import IPCServer
from gamebuddy.kin import Kin, KinCallbacks
from gamebuddy.llm import make_provider
from gamebuddy.llm.router import ProviderError, coach_model
from gamebuddy.memory import Store
from gamebuddy.ui.bridge import Bridge
from gamebuddy.ui.theme import THEME_DIR, omarchy_colors, stylesheet, theme_file
from gamebuddy.ui.widget import BuddyWidget

log = logging.getLogger(__name__)

# Engine error codes → i18n keys, so the friendly text follows the UI language.
_FRIENDLY = {
    "superwhisper_not_installed": "err_superwhisper_missing",
    "superwhisper_timeout": "err_superwhisper_timeout",
    "codex_not_installed": "err_codex_missing",
    "codex_not_logged_in": "err_codex_login",
    "codex_timeout": "err_codex_timeout",
    "voxtype_not_installed": "err_voxtype_missing",
    "voxtype_no_model": "err_voxtype_model",
    "voxtype_timeout": "err_voxtype_timeout",
    "missing_api_key": "err_missing_key",
}


def friendly_error(message: str, tr: Translator | None = None) -> str:
    translator = tr or Translator("en")
    for code, key in _FRIENDLY.items():
        if code in message:
            return translator(key)
    return message


class GameBuddyApp(QObject):
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
        self._timings: dict[str, float] = {}
        self._last_stt_text = ""

        self.kin = Kin(self.cfg, self.store, self._kin_callbacks())
        self.kin.language = self.tr.language

        self.widget = BuddyWidget(
            self.tr,
            self.cfg.general.assistant_name,
            self.cfg.hotkeys.push_to_talk,
            self.cfg.ui.width,
            self.cfg.ui.height,
            mode=self.cfg.ui.mode,
            compact_orb=self.cfg.ui.compact_orb,
        )
        self.widget.ptt_mode = self.cfg.hotkeys.mode
        self._apply_theme()
        self._apply_direction()
        self._watch_theme()
        self._apply_window_flags()
        self._connect()

    # ---- setup ---------------------------------------------------------------
    def _apply_theme(self) -> None:
        # Always follow the desktop: the active Omarchy palette, DEFAULT without one.
        colors = omarchy_colors()
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet(colors, self.cfg.ui.font_size, self.cfg.ui.opacity))
        self.widget.set_theme_colors(colors)

    def _apply_direction(self) -> None:
        """Arabic, Hebrew, Persian and Urdu read right to left; mirror the layout."""
        app = QApplication.instance()
        if app:
            app.setLayoutDirection(Qt.RightToLeft if is_rtl(self.tr.language) else Qt.LeftToRight)

    def _watch_theme(self) -> None:
        """Repaint when `omarchy theme set` swaps the palette, no restart needed."""
        self._theme_timer = QTimer(self)
        self._theme_timer.setSingleShot(True)
        self._theme_timer.setInterval(250)  # theme set writes several files in a row
        self._theme_timer.timeout.connect(self._on_theme_changed)
        self._theme_watcher = QFileSystemWatcher(self)
        for path in (str(THEME_DIR.parent), str(theme_file())):
            if Path(path).exists():
                self._theme_watcher.addPath(path)
        self._theme_watcher.directoryChanged.connect(lambda _p: self._theme_timer.start())
        self._theme_watcher.fileChanged.connect(lambda _p: self._theme_timer.start())

    def _on_theme_changed(self) -> None:
        path = str(theme_file())
        # QFileSystemWatcher drops unwatched files; the swapped symlink is a new one.
        if Path(path).is_file() and path not in self._theme_watcher.files():
            self._theme_watcher.addPath(path)
        self._apply_theme()

    def _apply_window_flags(self) -> None:
        flags = Qt.FramelessWindowHint | Qt.Window
        if self.cfg.ui.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.widget.setWindowFlags(flags)

    def _connect(self) -> None:
        w, b = self.widget, self.bridge
        b.stream_started.connect(w.begin_stream)
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
        b.update_available.connect(self._on_update_available)
        b.level.connect(w.set_level)
        b.coach_advice.connect(w.add_coach)
        b.command.connect(self._handle_command_gui)
        b.window_lost.connect(self._on_window_lost)
        b.memory.connect(lambda _n: w.set_status("ready"))
        w.mode_changed.connect(self._on_mode_changed)

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
        self._restore_window()
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
        if self.cfg.speech.tts == "piper":
            from gamebuddy.speech.tts import warm_piper_model

            self.pool.start(lambda: warm_piper_model(self.cfg))
        if self.cfg.speech.stt == "faster_whisper":
            from gamebuddy.speech.stt import warm_local_model

            self.pool.start(lambda: warm_local_model(self.cfg))
        if not self.cfg.ui.start_hidden:
            self.widget.show()
        if not self.cfg.general.onboarding_done:
            QTimer.singleShot(300, self.run_onboarding)
        if self.cfg.coach.enabled:
            QTimer.singleShot(1000, lambda: self.set_coach(True))
        self._update_info: dict | None = None
        if self.cfg.general.auto_update != "off" and not os.environ.get("GAMEBUDDY_NO_UPDATE_CHECK"):
            QTimer.singleShot(5000, self._check_update_async)

    def _on_mode_changed(self, mode: str) -> None:
        self.cfg.ui.mode = mode  # remembered across restarts (saved on quit / settings)

    # ---- updates -------------------------------------------------------------
    def _check_update_async(self) -> None:
        def work() -> None:
            try:
                from gamebuddy.update import check_for_update

                info = check_for_update()
            except Exception as exc:  # noqa: BLE001 — offline is fine
                log.debug("update check skipped: %s", exc)
                return
            if info.get("available"):
                self.bridge.update_available.emit(info)

        threading.Thread(target=work, name="update-check", daemon=True).start()

    def _on_update_available(self, info: dict) -> None:
        self._update_info = info
        self.widget.add_bubble(self.tr("update_available", version=info["latest"]), "bro")
        if self.tray is not None and getattr(self, "_update_action", None) is not None:
            self._update_action.setVisible(True)
            self._update_action.setText(self.tr("update_now", version=info["latest"]))

    def update_now(self) -> None:
        import shutil
        import subprocess

        exe = shutil.which("gamebuddy") or sys.argv[0]
        self.widget.add_bubble(self.tr("update_started"), "bro")
        subprocess.Popen(
            [exe, "update"], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

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
        # Keep the symbolic name so the tray host can tint Buddy to its theme.
        assets = str(files("gamebuddy") / "assets")
        if assets not in QIcon.fallbackSearchPaths():
            QIcon.setFallbackSearchPaths([*QIcon.fallbackSearchPaths(), assets])
        icon = QIcon.fromTheme("gamebuddy-symbolic")
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        self._ai_menu = menu.addMenu("IA / raisonnement" if self.tr.language == "fr" else "AI / reasoning")
        menu.aboutToShow.connect(self._refresh_ai_menu)
        self._refresh_ai_menu()
        for label, slot in (
            (self.tr("show"), self.toggle_visible),
            (self.tr("pick_window"), self.pick_window),
            (self.tr("hands_free_on"), self.toggle_hands_free),
            (self.tr("coach_on"), self.toggle_coach),
            (self.tr("settings"), self.open_settings),
            (self.tr("quit"), self.quit),
        ):
            act = QAction(label, menu)
            act.triggered.connect(slot)
            menu.addAction(act)
        self._update_action = QAction(self.tr("update_now", version=""), menu)
        self._update_action.triggered.connect(self.update_now)
        self._update_action.setVisible(False)
        menu.insertAction(menu.actions()[-1], self._update_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.toggle_visible() if reason == QSystemTrayIcon.Trigger else None
        )
        self.tray.setToolTip(
            f"GameBuddy — {self.cfg.llm.provider} / {self.cfg.llm.model or 'default'} / {self.cfg.llm.effort}"
        )
        self.tray.show()

    def _refresh_ai_menu(self) -> None:
        from gamebuddy.llm.catalog import codex_models, reasoning_levels

        menu = self._ai_menu
        menu.clear()
        fr = self.tr.language == "fr"
        cfg = self.cfg.llm
        menu.setEnabled(not self.kin.busy)
        current = menu.addAction(f"{cfg.provider} / {cfg.model or 'default'} / {cfg.effort}")
        current.setEnabled(False)
        if cfg.provider == "codex":
            models = menu.addMenu("Modèle" if fr else "Model")
            group = QActionGroup(models)
            models.addAction(
                self._ai_choice(
                    "Défaut Codex" if fr else "Codex default",
                    not cfg.model,
                    lambda: self._choose_ai(model=""),
                    group,
                )
            )
            for item in codex_models():
                slug = item["slug"]
                models.addAction(
                    self._ai_choice(
                        item.get("display_name") or slug,
                        cfg.model == slug,
                        lambda _checked=False, m=slug: self._choose_ai(model=m),
                        group,
                    )
                )
        levels = reasoning_levels(cfg.provider, cfg.model)
        if levels:
            effort_menu = menu.addMenu("Raisonnement" if fr else "Reasoning")
            group = QActionGroup(effort_menu)
            for effort in levels:
                effort_menu.addAction(
                    self._ai_choice(
                        effort,
                        cfg.effort == effort,
                        lambda _checked=False, e=effort: self._choose_ai(effort=e),
                        group,
                    )
                )
        menu.addSeparator()
        menu.addAction("Autre IA / modèle…" if fr else "Other provider / model…", self.open_ai_settings)

    def _ai_choice(self, label, checked, slot, group):
        action = QAction(label, group)
        action.setCheckable(True)
        action.setChecked(checked)
        group.addAction(action)
        action.triggered.connect(slot)
        return action

    def _choose_ai(self, model: str | None = None, effort: str | None = None) -> None:
        from gamebuddy.llm.catalog import reasoning_levels

        if self.kin.busy:
            return
        cfg = self.cfg.llm
        if model is not None:
            cfg.model = model
            levels = reasoning_levels(cfg.provider, model)
            if levels and cfg.effort not in levels:
                cfg.effort = levels[0]
        if effort is not None:
            if effort not in reasoning_levels(cfg.provider, cfg.model):
                return
            cfg.effort = effort
        save_config(self.cfg)
        self.kin.reset_provider()
        if self.coach:
            self.coach._provider = None
        self._refresh_ai_menu()
        self.tray.setToolTip(f"GameBuddy — {cfg.provider} / {cfg.model or 'default'} / {cfg.effort}")

    def open_ai_settings(self) -> None:
        self.open_settings(ai_tab=True)

    # ---- window selection ----------------------------------------------------
    def pick_window(self) -> None:
        from gamebuddy.ui.picker import WindowPicker

        dlg = WindowPicker(self.backend, self.tr, APP_ID, self.widget)
        if dlg.exec() and dlg.selected:
            self.select_window(dlg.selected)

    def _restore_window(self) -> None:
        """Re-select the window chosen last session when it is still open."""
        app_id, title = load_remembered_window()
        if not app_id:
            return
        try:
            window = find_same_window(self.backend.list_windows(), app_id, title)
        except Exception as exc:  # noqa: BLE001 — a missing window list is not an error
            log.debug("window memory skipped: %s", exc)
            return
        if window:
            self.select_window(window)

    def select_window(self, window: WindowInfo | None) -> None:
        self.window = window
        remember_window(window)
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
        # Direct Hyprland toplevel captures already exclude our separate window.
        if not self.cfg.capture.mask_overlay or self.backend.name == "hyprland":
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
            started = time.monotonic()
            self.kin.ask(text, shot)
            self._timings["assistant_s"] = round(time.monotonic() - started, 2)
            log.info("assistant response: %.2fs", self._timings["assistant_s"])
        except ProviderError as exc:
            key = "error_no_key" if "missing_api_key" in str(exc) else "error_generic"
            self.bridge.error.emit(self.tr(key, error=str(exc)))
        except Exception as exc:  # noqa: BLE001
            self.bridge.error.emit(self.tr("error_generic", error=friendly_error(str(exc), self.tr)))

    def _on_reply_done(self, text: str) -> None:
        self.widget.end_stream(text)
        if text.strip() and self.cfg.speech.speak_replies and self.cfg.speech.tts != "none":
            self.pool.start(lambda: self._speak(text))

    def _speak(self, text: str) -> None:
        from gamebuddy.audio import player
        from gamebuddy.speech.tts import synthesize

        try:
            started = time.monotonic()
            audio, fmt = synthesize(text, self.cfg, self.tr.language)
            self._timings["synthesis_s"] = round(time.monotonic() - started, 2)
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
        self.widget.add_error(friendly_error(message, self.tr))
        self.widget.set_status("ready")

    # ---- voice: push-to-talk -------------------------------------------------
    def ptt_start(self) -> None:
        if self.recorder and self.recorder.recording:
            return
        try:
            from gamebuddy.audio.recorder import Recorder

            if self.recorder is None:
                self.recorder = Recorder(
                    self.cfg.audio.sample_rate, self.cfg.audio.input_device, on_level=self.bridge.level.emit
                )
            from gamebuddy.audio import player

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
        from gamebuddy.speech.stt import transcribe

        started = time.monotonic()
        try:
            text = transcribe(wav, self.cfg)
            self._timings["transcription_s"] = round(time.monotonic() - started, 2)
            log.info("voice transcription: %.2fs", self._timings["transcription_s"])
        except Exception as exc:  # noqa: BLE001
            self.bridge.error.emit(self.tr("error_stt", error=str(exc)))
            return
        if not text.strip():
            self.bridge.status.emit("ready")
            return
        self.bridge.user_text.emit(text)
        self.bridge.stream_started.emit()
        shot = self.capture_game()
        try:
            started = time.monotonic()
            self.kin.ask(text, shot)
            self._timings["assistant_s"] = round(time.monotonic() - started, 2)
            log.info("assistant response: %.2fs", self._timings["assistant_s"])
        except ProviderError as exc:
            key = "error_no_key" if "missing_api_key" in str(exc) else "error_generic"
            self.bridge.error.emit(self.tr(key, error=str(exc)))
        except Exception as exc:  # noqa: BLE001
            self.bridge.error.emit(self.tr("error_generic", error=friendly_error(str(exc), self.tr)))

    # ---- voice: hands-free ---------------------------------------------------
    def toggle_hands_free(self) -> None:
        self.set_hands_free(not (self.listener and self.listener.active))

    def set_hands_free(self, on: bool) -> None:
        if on:
            try:
                from gamebuddy.audio.recorder import HandsFreeListener

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

    def open_settings(self, ai_tab: bool = False) -> None:
        from gamebuddy.ui.settings import SettingsDialog

        dlg = (
            SettingsDialog(self.cfg, self.tr, self.widget, ai_tab=True)
            if ai_tab
            else SettingsDialog(self.cfg, self.tr, self.widget)
        )
        if dlg.exec():
            self.tr.set_language(self.cfg.general.language)
            self._apply_direction()
            self.kin.language = self.tr.language
            self.kin.reset_provider()
            if self.tray:
                self._refresh_ai_menu()
                cfg = self.cfg.llm
                self.tray.setToolTip(f"GameBuddy — {cfg.provider} / {cfg.model or 'default'} / {cfg.effort}")
            if self.coach:
                self.coach._provider = None
            hands_free = bool(self.listener and self.listener.active)
            if self.listener:
                self.listener.stop()
            self.listener = None
            if self.recorder:
                if self.recorder.recording:
                    self.recorder.stop()
                    self.widget.set_recording(False)
                self.recorder = None
            if hands_free:
                self.set_hands_free(True)
            self._apply_theme()
            self.widget.title.setText(self.cfg.general.assistant_name)
            if self.cfg.speech.stt == "faster_whisper":
                from gamebuddy.speech.stt import warm_local_model

                self.pool.start(lambda: warm_local_model(self.cfg))
            self.widget.ptt_key = self.cfg.hotkeys.push_to_talk
            self.widget.ptt_mode = self.cfg.hotkeys.mode
            self.widget.set_window_title(self.window.title if self.window else None)

    def run_onboarding(self) -> None:
        from gamebuddy.ui.onboarding import OnboardingWizard

        wiz = OnboardingWizard(self.cfg, self.tr, self.backend, self.widget)
        if wiz.exec():
            self.tr.set_language(self.cfg.general.language)
            self._apply_direction()
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
            "provider": self.cfg.llm.provider,
            "model": self.cfg.llm.model or "default",
            "effort": self.cfg.llm.effort,
            "talk_shortcut": self.cfg.hotkeys.push_to_talk,
            "talk_mode": self.cfg.hotkeys.mode,
            "timings": dict(self._timings),
            "language": self.tr.language,
        }

    def _handle_command_threadsafe(self, req: dict[str, Any]) -> dict[str, Any]:
        cmd = req.get("cmd")
        if cmd == "ping":
            return {"ok": True, "app": "gamebuddy"}
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
        if cmd == "ask" and req.get("wait"):
            # Scriptable ask: answer on this connection instead of queueing to the UI.
            return self._ask_blocking(str(req.get("text", "")).strip())
        self.bridge.command.emit(req)
        return {"ok": True, "queued": cmd}

    def _ask_blocking(self, text: str) -> dict[str, Any]:
        """One exchange on the calling thread; returns the reply text or the error."""
        if not text:
            return {"ok": False, "error": "empty question"}
        if self.kin.busy:
            return {"ok": False, "error": "busy — another question is being answered"}
        self.bridge.user_text.emit(text)
        self.bridge.stream_started.emit()
        reply = self.kin.ask(text, self.capture_game())
        if reply.strip():
            return {"ok": True, "reply": reply}
        return {"ok": False, "error": friendly_error(self.kin.last_error or "no answer", self.tr)}

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
        elif cmd == "ai-settings":
            self.open_ai_settings()
        elif cmd == "settings":
            self.open_settings()
        elif cmd == "quit":
            self.quit()


def run_app(argv: list[str] | None = None) -> int:
    import sys

    QGuiApplication.setDesktopFileName(APP_ID)
    app = QApplication(argv or sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName("GameBuddy")
    app.setQuitOnLastWindowClosed(False)
    gb = GameBuddyApp()
    try:
        gb.start()
    except RuntimeError as exc:
        print(f"gamebuddy: {exc}", file=sys.stderr)
        return 2
    return app.exec()
