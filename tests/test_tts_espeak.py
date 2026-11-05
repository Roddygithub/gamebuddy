from pathlib import Path
from types import SimpleNamespace

from gamebuddy.config import Config
from gamebuddy.speech import tts


def test_espeak_receives_private_reply_on_stdin_not_argv(monkeypatch):
    secret_reply = "Your private reply contains a memorable detail."
    observed = {}
    monkeypatch.setattr(tts.shutil, "which", lambda name: f"/usr/bin/{name}")

    def run(args, **kwargs):
        observed["args"] = args
        observed["input"] = kwargs["input"]
        Path(args[args.index("-w") + 1]).write_bytes(b"wav-data")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tts.subprocess, "run", run)

    audio = tts._espeak(secret_reply, "en")

    assert audio == b"wav-data"
    assert secret_reply not in observed["args"]
    assert observed["input"] == secret_reply.encode("utf-8")


def test_piper_cli_keeps_reply_off_argv(monkeypatch):
    monkeypatch.setattr(tts, "find_spec", lambda _: None)
    monkeypatch.setattr(tts.shutil, "which", lambda _: "/usr/bin/piper")
    paths = []

    def run(args, **kwargs):
        assert args[0] == "/usr/bin/piper"
        assert "Private reply" not in args
        assert kwargs["input"] == b"Private reply"
        path = Path(args[args.index("--output_file") + 1])
        paths.append(path)
        path.write_bytes(b"wav-data")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tts.subprocess, "run", run)
    cfg = Config()
    cfg.speech.tts = "piper"
    cfg.speech.piper_model = "/voices/fr_FR-siwis-medium.onnx"
    assert tts.synthesize("Private reply", cfg, "fr") == (b"wav-data", "wav")
    assert not paths[0].exists()


def test_piper_reuses_warmed_voice_and_changes_model(monkeypatch):
    import io
    import sys
    import wave

    loaded = []
    spoken = []

    class Voice:
        @staticmethod
        def load(model):
            loaded.append(model)
            return Voice()

        def synthesize_wav(self, text, wav):
            spoken.append(text)
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\x00\x00" * 8)

    monkeypatch.setitem(sys.modules, "piper", SimpleNamespace(PiperVoice=Voice))
    monkeypatch.setattr(tts, "find_spec", lambda _: object())
    cfg = Config()
    cfg.speech.tts = "piper"
    cfg.speech.piper_model = "/voices/fr.onnx"
    tts._piper_voice.cache_clear()
    try:
        tts.warm_piper_model(cfg)
        assert spoken == []
        for _ in range(2):
            audio, _ = tts.synthesize("Bonjour", cfg, "fr")
            with wave.open(io.BytesIO(audio)) as wav:
                assert wav.getnframes() == 8
        assert loaded == ["/voices/fr.onnx"]
        cfg.speech.piper_model = "/voices/other.onnx"
        tts.synthesize("Salut", cfg, "fr")
        assert loaded == ["/voices/fr.onnx", "/voices/other.onnx"]
    finally:
        tts._piper_voice.cache_clear()
