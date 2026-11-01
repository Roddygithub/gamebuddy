from pathlib import Path
from types import SimpleNamespace

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
