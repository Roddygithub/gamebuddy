"""Settings dialog — writes config.toml."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gamebuddy.config import SUPPORTED_LANGUAGES, Config, save_config
from gamebuddy.i18n import Translator, language_display_name

PROVIDERS = ["codex", "anthropic", "openai", "ollama", "openai_compatible"]
STT = ["openai", "voxtype", "faster_whisper", "whispercpp", "none"]
TTS = ["openai", "piper", "espeak", "none"]


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, tr: Translator, parent=None, ai_tab: bool = False):
        super().__init__(parent)
        self.cfg = cfg
        self.tr = tr
        self.setWindowTitle(tr("settings"))
        self.resize(520, 520)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ---- general ---------------------------------------------------
        general = QWidget()
        f = QFormLayout(general)
        self.language = QComboBox()
        self.language.addItem("auto", "auto")
        for code in SUPPORTED_LANGUAGES:
            self.language.addItem(language_display_name(code), code)
        self.language.setCurrentIndex(max(0, self.language.findData(cfg.general.language)))
        self.name = QLineEdit(cfg.general.assistant_name)
        self.personality = QComboBox()
        self.personality.addItems(["coach", "friendly", "concise"])
        self.personality.setCurrentText(cfg.general.personality)
        from gamebuddy.hotkeys import binding_to_sequence

        self.ptt = QKeySequenceEdit(QKeySequence(binding_to_sequence(cfg.hotkeys.push_to_talk)))
        self.ptt.setMaximumSequenceLength(1)
        self.toggle_key = QKeySequenceEdit(QKeySequence(binding_to_sequence(cfg.hotkeys.toggle_widget)))
        self.toggle_key.setMaximumSequenceLength(1)
        self.ptt_mode = QComboBox()
        self.ptt_mode.addItem("Maintenir pour parler" if tr.language == "fr" else "Hold to talk", "hold")
        self.ptt_mode.addItem(
            "Appuyer pour démarrer / arrêter" if tr.language == "fr" else "Press to start / stop", "toggle"
        )
        self.ptt_mode.setCurrentIndex(max(0, self.ptt_mode.findData(cfg.hotkeys.mode)))
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.3, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.setValue(cfg.ui.opacity)
        self.font_size = QSpinBox()
        self.font_size.setRange(10, 20)
        self.font_size.setValue(cfg.ui.font_size)
        f.addRow(tr("onboarding_lang"), self.language)
        f.addRow("Name", self.name)
        f.addRow("Personality", self.personality)
        self.auto_update = QComboBox()
        self.auto_update.addItems(["off", "notify", "auto"])
        self.auto_update.setCurrentText(cfg.general.auto_update)
        f.addRow("Updates", self.auto_update)
        f.addRow("Parler" if tr.language == "fr" else "Talk shortcut", self.ptt)
        f.addRow("Mode micro" if tr.language == "fr" else "Microphone mode", self.ptt_mode)
        f.addRow("Afficher / masquer" if tr.language == "fr" else "Show / hide", self.toggle_key)
        self.ui_mode = QComboBox()
        self.ui_mode.addItems(["orb", "panel"])
        self.ui_mode.setCurrentText(cfg.ui.mode)
        f.addRow("Start as", self.ui_mode)
        f.addRow("Opacity", self.opacity)
        f.addRow("Font size", self.font_size)
        tabs.addTab(general, "General")

        # ---- AI --------------------------------------------------------
        ai = QWidget()
        f = QFormLayout(ai)
        self.provider = QComboBox()
        self.provider.addItems(PROVIDERS)
        self.provider.setCurrentText(cfg.llm.provider)
        self.model = QLineEdit(cfg.llm.model)
        self.base_url = QLineEdit(cfg.llm.base_url)
        self.base_url.setPlaceholderText("http://localhost:11434/v1")
        self.api_key = QLineEdit(cfg.llm.api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("leave empty to use the environment variable")
        self.effort = QComboBox()

        def sync_effort():
            from gamebuddy.llm.catalog import reasoning_levels

            previous = self.effort.currentText() or cfg.llm.effort
            levels = reasoning_levels(self.provider.currentText(), self.model.text().strip())
            self.effort.clear()
            self.effort.addItems(levels)
            self.effort.setEnabled(bool(levels))
            if previous in levels:
                self.effort.setCurrentText(previous)

        self.provider.currentTextChanged.connect(sync_effort)
        self.model.textChanged.connect(sync_effort)
        sync_effort()
        self.vision = QCheckBox()
        self.vision.setChecked(cfg.llm.vision)
        self.web = QCheckBox()
        self.web.setChecked(cfg.llm.web_search)
        self.screenshot = QCheckBox()
        self.screenshot.setChecked(cfg.capture.attach_screenshot)
        f.addRow(tr("onboarding_provider"), self.provider)
        note = QLabel(
            "codex = your ChatGPT Plus/Pro subscription through the Codex CLI (run `codex login` once, no API key)"
        )
        note.setWordWrap(True)
        f.addRow(note)
        f.addRow("Model", self.model)
        f.addRow("Base URL", self.base_url)
        f.addRow(tr("onboarding_key"), self.api_key)
        f.addRow("Reasoning (Codex / Anthropic)", self.effort)
        f.addRow("Vision", self.vision)
        f.addRow("Web search", self.web)
        f.addRow("Attach game screenshot", self.screenshot)
        tabs.addTab(ai, "AI")
        if ai_tab:
            tabs.setCurrentWidget(ai)

        # ---- voice -----------------------------------------------------
        voice = QWidget()
        f = QFormLayout(voice)
        self.stt = QComboBox()
        self.stt.addItems(STT)
        self.stt.setCurrentText(cfg.speech.stt)
        self.stt_model = QComboBox()
        self.stt_model.setEditable(True)
        self.stt_model.addItems(["tiny", "base", "small", "medium", "whisper-1"])
        self.stt_model.setCurrentText(cfg.speech.stt_model)
        self.stt_model.setToolTip(
            "Whisper local : tiny = rapide ; base = équilibré ; small/medium = plus lourds."
        )
        self.tts = QComboBox()
        self.tts.addItems(TTS)
        self.tts.setCurrentText(cfg.speech.tts)
        self.tts_voice = QLineEdit(cfg.speech.tts_voice)
        self.piper_model = QLineEdit(cfg.speech.piper_model)
        self.speak = QCheckBox()
        self.speak.setChecked(cfg.speech.speak_replies)
        self.input_device = QLineEdit(cfg.audio.input_device)
        self.vad = QDoubleSpinBox()
        self.vad.setDecimals(3)
        self.vad.setRange(0.001, 0.5)
        self.vad.setSingleStep(0.005)
        self.vad.setValue(cfg.audio.vad_threshold)
        f.addRow("Speech to text", self.stt)
        f.addRow("STT model", self.stt_model)
        stt_note = QLabel(
            "voxtype: Omarchy's dictation tool (Install > AI > Dictation) — reuses its Whisper/Parakeet model "
            "and GPU build. STT model is left empty to use voxtype's own config."
        )
        stt_note.setWordWrap(True)
        f.addRow(stt_note)
        f.addRow("Text to speech", self.tts)
        f.addRow("TTS voice", self.tts_voice)
        f.addRow("Piper model path", self.piper_model)
        f.addRow("Speak replies", self.speak)
        f.addRow("Input device", self.input_device)
        f.addRow("Voice threshold", self.vad)
        tabs.addTab(voice, "Voice")

        # ---- coach -----------------------------------------------------
        coach = QWidget()
        f = QFormLayout(coach)
        self.coach_enabled = QCheckBox()
        self.coach_enabled.setChecked(cfg.coach.enabled)
        self.coach_interval = QDoubleSpinBox()
        self.coach_interval.setRange(1.0, 60.0)
        self.coach_interval.setValue(cfg.coach.interval_s)
        self.coach_model = QLineEdit(cfg.coach.model)
        self.coach_model.setPlaceholderText("cheap default for the provider")
        self.coach_conf = QDoubleSpinBox()
        self.coach_conf.setRange(0.3, 1.0)
        self.coach_conf.setSingleStep(0.05)
        self.coach_conf.setValue(cfg.coach.min_confidence)
        self.coach_cooldown = QSpinBox()
        self.coach_cooldown.setRange(5, 600)
        self.coach_cooldown.setValue(cfg.coach.cooldown_s)
        self.coach_speak = QCheckBox()
        self.coach_speak.setChecked(cfg.coach.speak)
        f.addRow("Enabled at start", self.coach_enabled)
        f.addRow("Interval (s)", self.coach_interval)
        f.addRow("Model", self.coach_model)
        f.addRow("Min confidence", self.coach_conf)
        f.addRow("Cooldown (s)", self.coach_cooldown)
        f.addRow("Speak advice", self.coach_speak)
        tabs.addTab(coach, "Coach")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        from dataclasses import replace

        from gamebuddy.hotkeys import apply_hypr_bindings, sequence_to_binding

        c = self.cfg
        try:
            hotkeys = replace(
                c.hotkeys,
                push_to_talk=sequence_to_binding(
                    self.ptt.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                ),
                toggle_widget=sequence_to_binding(
                    self.toggle_key.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                ),
                mode=self.ptt_mode.currentData(),
            )
            if hotkeys.push_to_talk == hotkeys.toggle_widget:
                raise ValueError("Les deux raccourcis doivent être différents.")
            if hotkeys != c.hotkeys:
                applied = apply_hypr_bindings(hotkeys, c.hotkeys)
                if not applied:
                    QMessageBox.information(
                        self,
                        "Raccourcis",
                        "Raccourcis enregistrés. Actualise aussi les raccourcis globaux dans les réglages de ton bureau (ou avec gamebuddy hyprland-config / sway-config).",
                    )
        except Exception as exc:  # surface compositor reload/validation failures without losing the dialog
            QMessageBox.warning(self, "Raccourcis", str(exc))
            return
        c.general.language = self.language.currentData()
        c.general.assistant_name = self.name.text().strip() or "Buddy"
        c.general.personality = self.personality.currentText()
        c.general.auto_update = self.auto_update.currentText()
        c.hotkeys = hotkeys
        c.ui.opacity = self.opacity.value()
        c.ui.mode = self.ui_mode.currentText()
        c.ui.font_size = self.font_size.value()
        c.llm.provider = self.provider.currentText()
        c.llm.model = self.model.text().strip()
        c.llm.base_url = self.base_url.text().strip()
        c.llm.api_key = self.api_key.text().strip()
        c.llm.effort = self.effort.currentText()
        c.llm.vision = self.vision.isChecked()
        c.llm.web_search = self.web.isChecked()
        c.capture.attach_screenshot = self.screenshot.isChecked()
        c.speech.stt = self.stt.currentText()
        c.speech.stt_model = self.stt_model.currentText().strip()
        if c.speech.stt == "voxtype":
            c.speech.voxtype_model = c.speech.stt_model
        c.speech.tts = self.tts.currentText()
        c.speech.tts_voice = self.tts_voice.text().strip()
        c.speech.piper_model = self.piper_model.text().strip()
        c.speech.speak_replies = self.speak.isChecked()
        c.audio.input_device = self.input_device.text().strip()
        c.audio.vad_threshold = self.vad.value()
        c.coach.enabled = self.coach_enabled.isChecked()
        c.coach.interval_s = self.coach_interval.value()
        c.coach.model = self.coach_model.text().strip()
        c.coach.min_confidence = self.coach_conf.value()
        c.coach.cooldown_s = self.coach_cooldown.value()
        c.coach.speak = self.coach_speak.isChecked()
        save_config(c)
        self.accept()
