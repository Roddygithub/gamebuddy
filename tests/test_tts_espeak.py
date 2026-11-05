from pathlib import Path
from types import SimpleNamespace

import pytest

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


@pytest.mark.parametrize("module_available", [True, False])
def test_piper_uses_venv_or_cli_and_keeps_reply_off_argv(monkeypatch, module_available):
    import sys

    monkeypatch.setattr(tts, "find_spec", lambda _: object() if module_available else None)
    monkeypatch.setattr(tts.shutil, "which", lambda _: "/usr/bin/piper")
    paths = []

    def run(args, **kwargs):
        expected = [sys.executable, "-m", "piper"] if module_available else ["/usr/bin/piper"]
        assert args[: len(expected)] == expected
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
