import sys
from types import SimpleNamespace

from gamebuddy.config import Config
from gamebuddy.speech import stt


def test_local_model_reloads_when_settings_change(monkeypatch):
    created = []

    class Model:
        def __init__(self, size, **kwargs):
            created.append(size)

        def transcribe(self, *args, **kwargs):
            return iter([SimpleNamespace(text="hello")]), None

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    monkeypatch.setattr(stt, "_local_model", None)
    monkeypatch.setattr(stt, "_local_model_size", None)
    cfg = Config()
    cfg.speech.stt_model = "base"
    assert stt._faster_whisper(b"wav", cfg) == "hello"
    stt._faster_whisper(b"wav", cfg)
    cfg.speech.stt_model = "tiny"
    stt._faster_whisper(b"wav", cfg)
    assert created == ["base", "tiny"]


def test_background_warmup_never_downloads_missing_model(monkeypatch):
    calls = []

    class Missing:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs)
            raise ValueError("not cached")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Missing))
    monkeypatch.setattr(stt, "_local_model", None)
    monkeypatch.setattr(stt, "_local_model_size", None)
    cfg = Config()
    cfg.speech.stt = "faster_whisper"
    stt.warm_local_model(cfg)
    assert len(calls) == 1 and calls[0]["local_files_only"] is True
    assert stt._local_model is None
