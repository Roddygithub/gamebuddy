"""The dictation service is asynchronous: only consume the session we submitted."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from gamebuddy.config import Config
from gamebuddy.speech import stt


def test_waits_for_own_session_without_pasting_and_removes_audio(monkeypatch):
    replies = iter(
        [
            {"ok": True, "session_id": 8},
            None,
            {"session_id": 7, "text": "unrelated private dictation"},
            {"session_id": 8, "text": " Bonjour Buddy "},
        ]
    )
    commands = []
    paths = []

    def run(command, **kwargs):
        commands.append(command)
        if command[1] == "transcribe":
            path = Path(command[2])
            assert path.read_bytes() == b"RIFFtest"
            assert path.parent.stat().st_mode & 0o777 == 0o700
            paths.append(path)
        return SimpleNamespace(returncode=0, stdout=json.dumps(next(replies)))

    monkeypatch.setattr(stt.shutil, "which", lambda _: "/usr/bin/superwhisper")
    monkeypatch.setattr(stt.subprocess, "run", run)
    monkeypatch.setattr(stt.time, "sleep", lambda _: None)
    cfg = Config()
    cfg.speech.stt = "superwhisper"
    assert stt.transcribe(b"RIFFtest", cfg) == "Bonjour Buddy"
    assert commands == [
        ["superwhisper", "transcribe", str(paths[0])],
        ["superwhisper", "read"],
        ["superwhisper", "read"],
        ["superwhisper", "read"],
    ]
    assert not paths[0].parent.exists()


@pytest.mark.parametrize(
    "response",
    [
        {"session_id": 9, "text": "another dictation"},
        {"session_id": 8, "error": "transcription failed"},
        {"session_id": 8, "text": None},
        [],
    ],
)
def test_rejects_replaced_sessions_and_failed_or_invalid_results(monkeypatch, response):
    replies = iter([{"ok": True, "session_id": 8}, response])
    monkeypatch.setattr(stt.shutil, "which", lambda _: "/usr/bin/superwhisper")
    monkeypatch.setattr(
        stt.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(next(replies)))
    )
    with pytest.raises(stt.STTError, match="superwhisper_failed"):
        stt._superwhisper(b"RIFFtest")


def test_timeout_removes_audio(monkeypatch):
    paths = []

    def run(command, **kwargs):
        paths.append(Path(command[2]))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(stt.shutil, "which", lambda _: "/usr/bin/superwhisper")
    monkeypatch.setattr(stt.subprocess, "run", run)
    with pytest.raises(stt.STTError, match="superwhisper_timeout"):
        stt._superwhisper(b"RIFFtest")
    assert not paths[0].parent.exists()


def test_missing_binary(monkeypatch):
    monkeypatch.setattr(stt.shutil, "which", lambda _: None)
    with pytest.raises(stt.STTError, match="superwhisper_not_installed"):
        stt._superwhisper(b"RIFFtest")
