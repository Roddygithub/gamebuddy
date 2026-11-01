"""First-run wizard: language → provider & key → microphone → game window."""

from __future__ import annotations

import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from gamebro.capture import CaptureBackend, WindowInfo
from gamebro.config import SUPPORTED_LANGUAGES, Config, save_config
from gamebro.i18n import Translator, language_display_name
from gamebro.ui.settings import PROVIDERS

DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-4o",
    "ollama": "llama3.2-vision",
    "openai_compatible": "",
}


class OnboardingWizard(QWizard):
    def __init__(self, cfg: Config, tr: Translator, backend: CaptureBackend, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.tr = tr
        self.backend = backend
        self.selected_window: WindowInfo | None = None
        self.setWindowTitle(tr("onboarding_title"))
        self.setWizardStyle(QWizard.ModernStyle)
        self.resize(560, 460)
        self.setButtonText(QWizard.NextButton, tr("next"))
        self.setButtonText(QWizard.BackButton, tr("back"))
        self.setButtonText(QWizard.FinishButton, tr("finish"))
        self.setButtonText(QWizard.CancelButton, tr("cancel"))
        self.addPage(self._page_language())
        self.addPage(self._page_provider())
        self.addPage(self._page_mic())
        self.addPage(self._page_window())
        self.addPage(self._page_done())

    # ---- pages -------------------------------------------------------------
    def _page_language(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(self.tr("onboarding_lang"))
        layout = QFormLayout(page)
        self.language = QComboBox()
        self.language.addItem("auto", "auto")
        for code in SUPPORTED_LANGUAGES:
            self.language.addItem(language_display_name(code), code)
        self.language.setCurrentIndex(max(0, self.language.findData(self.cfg.general.language)))
        self.name = QLineEdit(self.cfg.general.assistant_name)
        layout.addRow(self.tr("onboarding_lang"), self.language)
        layout.addRow("Name", self.name)
        return page

    def _page_provider(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(self.tr("onboarding_provider"))
        layout = QFormLayout(page)
        self.provider = QComboBox()
        self.provider.addItems(PROVIDERS)
        self.provider.setCurrentText(self.cfg.llm.provider)
        self.model = QLineEdit(self.cfg.llm.model)
        self.base_url = QLineEdit(self.cfg.llm.base_url)
        self.api_key = QLineEdit(self.cfg.llm.api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.openai_key = QLineEdit()
        self.openai_key.setEchoMode(QLineEdit.Password)
        self.openai_key.setPlaceholderText("optional — for OpenAI voice (STT/TTS)")
        self.provider.currentTextChanged.connect(lambda p: self.model.setText(DEFAULT_MODELS.get(p, "")))
        layout.addRow(self.tr("onboarding_provider"), self.provider)
        layout.addRow("Model", self.model)
        layout.addRow("Base URL", self.base_url)
        layout.addRow(self.tr("onboarding_key"), self.api_key)
        layout.addRow("OPENAI_API_KEY", self.openai_key)
        note = QLabel(
            "Keys are stored in ~/.config/gamebro/config.toml (chmod 600). Environment variables also work."
        )
        note.setWordWrap(True)
        layout.addRow(note)
        return page

    def _page_mic(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(self.tr("onboarding_mic"))
        layout = QVBoxLayout(page)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.mic_status = QLabel("")
        self.mic_status.setWordWrap(True)
        layout.addWidget(QLabel(self.tr("onboarding_level")))
        layout.addWidget(self.level)
        layout.addWidget(self.mic_status)
        self._recorder = None
        self._level_value = 0.0

        def on_level(v: float) -> None:
            self._level_value = v

        timer = QTimer(page)
        timer.setInterval(60)
        timer.timeout.connect(lambda: self.level.setValue(int(min(1.0, self._level_value * 8) * 100)))

        def enter() -> None:
            try:
                from gamebro.audio.recorder import Recorder

                self._recorder = Recorder(
                    self.cfg.audio.sample_rate, self.cfg.audio.input_device, on_level=on_level
                )
                self._recorder.start()
                timer.start()
                self.mic_status.setText("")
            except Exception as exc:  # noqa: BLE001
                self.mic_status.setText(self.tr("error_mic", error=str(exc)))

        def leave() -> None:
            timer.stop()
            if self._recorder is not None:
                try:
                    self._recorder.stop()
                except Exception:  # noqa: BLE001
                    pass
                self._recorder = None

        page.initializePage = enter  # type: ignore[method-assign]
        page.cleanupPage = leave  # type: ignore[method-assign]
        self.currentIdChanged.connect(lambda _id: leave() if self.currentPage() is not page else None)
        return page

    def _page_window(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(self.tr("onboarding_window"))
        layout = QVBoxLayout(page)
        self.windows = QListWidget()
        layout.addWidget(self.windows)

        def enter() -> None:
            self.windows.clear()
            try:
                for w in self.backend.list_windows():
                    if w.app_id.lower() == "gamebro":
                        continue
                    item = QListWidgetItem(w.label)
                    item.setData(0x0100, w)
                    self.windows.addItem(item)
            except Exception as exc:  # noqa: BLE001
                self.windows.addItem(self.tr("error_generic", error=str(exc)))

        page.initializePage = enter  # type: ignore[method-assign]
        return page

    def _page_done(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(self.tr("finish"))
        layout = QVBoxLayout(page)
        label = QLabel(self.tr("onboarding_done", key=self.cfg.hotkeys.push_to_talk.replace(", ", "+")))
        label.setWordWrap(True)
        layout.addWidget(label)
        return page

    # ---- result ------------------------------------------------------------
    def accept(self) -> None:
        c = self.cfg
        c.general.language = self.language.currentData()
        c.general.assistant_name = self.name.text().strip() or "Bro"
        c.llm.provider = self.provider.currentText()
        c.llm.model = self.model.text().strip() or DEFAULT_MODELS.get(c.llm.provider, "")
        c.llm.base_url = self.base_url.text().strip()
        c.llm.api_key = self.api_key.text().strip()
        if self.openai_key.text().strip():
            os.environ["OPENAI_API_KEY"] = self.openai_key.text().strip()
            if c.llm.provider == "openai" and not c.llm.api_key:
                c.llm.api_key = self.openai_key.text().strip()
        if not os.environ.get("OPENAI_API_KEY") and not (c.llm.provider == "openai"):
            # No OpenAI key at all: pick offline-friendly speech engines.
            c.speech.stt = "faster_whisper" if c.speech.stt == "openai" else c.speech.stt
            c.speech.tts = "espeak" if c.speech.tts == "openai" else c.speech.tts
        item = self.windows.currentItem()
        if item is not None and item.data(0x0100):
            self.selected_window = item.data(0x0100)
        c.general.onboarding_done = True
        save_config(c)
        super().accept()
