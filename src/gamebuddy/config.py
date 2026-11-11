"""Configuration: a TOML file with sane defaults.

Every section is a dataclass so the rest of the code gets attribute access and
type hints. Unknown keys in the file are ignored; missing keys take defaults.
"""

from __future__ import annotations

import dataclasses
import os
import tempfile
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import tomli_w

from gamebuddy import ASSISTANT_DEFAULT_NAME
from gamebuddy.paths import config_file, ensure_dirs


@dataclass
class GeneralConfig:
    language: str = "auto"  # auto | fr | en | de | es | it | pt-BR | pt-PT
    assistant_name: str = ASSISTANT_DEFAULT_NAME
    personality: str = "coach"  # coach | friendly | concise
    onboarding_done: bool = False
    auto_update: str = "notify"  # off | notify | auto (daily systemd timer installs releases)


@dataclass
class HotkeyConfig:
    # Hyprland bind syntax (MODS, KEY). Used by `gamebuddy hyprland-config`.
    push_to_talk: str = "ALT, V"
    toggle_widget: str = "ALT, B"
    mode: str = "hold"  # hold | toggle
    x11_listener: bool = False  # use pynput global listener on X11 sessions


@dataclass
class LLMConfig:
    provider: str = (
        "anthropic"  # anthropic | openai | ollama | openai_compatible | codex (ChatGPT Plus, no key)
    )
    model: str = "claude-opus-5-5"
    base_url: str = ""  # for ollama / openai_compatible (e.g. http://localhost:11434/v1)
    api_key: str = ""  # prefer api_key_env; stored 0600 if set here
    api_key_env: str = ""  # defaults to ANTHROPIC_API_KEY / OPENAI_API_KEY by provider
    max_tokens: int = 2048
    effort: str = "low"  # anthropic / codex: low | medium | high
    codex_binary: str = "codex"  # Codex CLI executable (provider = codex)
    temperature: float = 0.6  # openai-compatible only
    vision: bool = True
    web_search: bool = True
    max_tool_rounds: int = 4
    history_messages: int = 30


@dataclass
class SpeechConfig:
    stt: str = "openai"  # openai | superwhisper | voxtype | faster_whisper | whispercpp | none
    stt_model: str = "whisper-1"
    stt_language: str = ""  # "" = auto-detect
    whispercpp_binary: str = "whisper-cli"
    whispercpp_model: str = ""
    voxtype_binary: str = "voxtype"  # Omarchy dictation tool; reuses its model + GPU build
    voxtype_model: str = ""  # "" = voxtype's own config
    tts: str = "openai"  # openai | piper | espeak | none
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    piper_model: str = ""
    speak_replies: bool = True


@dataclass
class AudioConfig:
    input_device: str = ""  # sounddevice name or index, "" = default
    output_device: str = ""
    sample_rate: int = 16000
    vad_threshold: float = 0.015  # RMS, 0..1
    vad_silence_ms: int = 900
    vad_max_utterance_s: int = 30
    listening_idle_sleep_s: int = 120  # hands-free mode sleeps after this much silence


@dataclass
class CaptureConfig:
    backend: str = "auto"  # auto | hyprland | sway | wlroots | portal (GNOME/KDE) | x11 | macos | none
    attach_screenshot: bool = True
    max_width: int = 2560
    jpeg_quality: int = 90
    mask_overlay: bool = True


@dataclass
class CoachConfig:
    enabled: bool = False
    interval_s: float = 4.0
    min_change: float = 0.12  # normalized perceptual-hash distance to count as a change
    model: str = ""  # "" = same provider, cheap default per provider
    min_confidence: float = 0.7
    cooldown_s: int = 60
    speak: bool = False
    save_frames: bool = False  # keep candidate frames on disk to build eval cases later


@dataclass
class UIConfig:
    compact_orb: bool | str = "auto"  # auto adapts to logical screen size; true/false overrides
    width: int = 420
    height: int = 640
    opacity: float = 0.94
    always_on_top: bool = True
    start_hidden: bool = False
    font_size: int = 13
    mode: str = "orb"  # orb (avatar + last words, click to open) | panel (full chat window)


@dataclass
class Config:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    speech: SpeechConfig = field(default_factory=SpeechConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    coach: CoachConfig = field(default_factory=CoachConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    # ---- helpers -------------------------------------------------------
    def resolve_api_key(self) -> str:
        if self.llm.api_key:
            return self.llm.api_key
        env = self.llm.api_key_env or DEFAULT_KEY_ENV.get(self.llm.provider, "")
        return os.environ.get(env, "") if env else ""

    def openai_key(self) -> str:
        """Key used by OpenAI speech services, independent of the chat provider."""
        if self.llm.provider == "openai" and self.llm.api_key:
            return self.llm.api_key
        return os.environ.get("OPENAI_API_KEY", "")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


DEFAULT_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "ollama": "",
    "openai_compatible": "OPENAI_API_KEY",
    "codex": "",
}

CHEAP_COACH_MODEL = {
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-4o-mini",
    "ollama": "",  # same model
    "openai_compatible": "",
    "codex": "",  # Codex picks its default model
}


def _from_dict(cls: type, data: dict[str, Any]) -> Any:
    kwargs = {}
    for f in fields(cls):
        if f.name in data:
            kwargs[f.name] = data[f.name]
    return cls(**kwargs)


def load_config(path: Path | None = None) -> Config:
    path = path or config_file()
    cfg = Config()
    if not path.is_file():
        return cfg
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    for section in fields(Config):
        if section.name in raw and isinstance(raw[section.name], dict):
            setattr(cfg, section.name, _from_dict(section.default_factory, raw[section.name]))  # type: ignore[arg-type]
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> Path:
    path = path or config_file()
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = cfg.to_dict()
    # mkstemp creates the file with mode 0600 before any secret is written.
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            tomli_w.dump(data, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path
