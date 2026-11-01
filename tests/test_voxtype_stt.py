"""voxtype STT engine: parse `voxtype transcribe` output and drive a fake binary."""

import os
import stat

import pytest

from gamebuddy.config import Config
from gamebuddy.speech.stt import STTError, parse_voxtype_output, transcribe, voxtype_available

SAMPLE = """Loading audio file: "/tmp/x.wav"
Audio format: 16000 Hz, 1 channel(s), Int
Processing 48000 samples (3.00s)...
VAD: 2.10s speech (70.0% of audio)

Where is the next save point?
"""


def test_parse_takes_text_after_last_blank_line():
    assert parse_voxtype_output(SAMPLE) == "Where is the next save point?"


def test_parse_no_speech():
    assert (
        parse_voxtype_output(SAMPLE.split("\n\n")[0] + "\nNo speech detected, skipping transcription.\n")
        == ""
    )


def test_parse_bare_transcript():
    assert parse_voxtype_output("hello there\n") == "hello there"


@pytest.fixture
def fake_voxtype(tmp_path, monkeypatch):
    script = tmp_path / "voxtype"
    log = tmp_path / "args.txt"
    script.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$@" > "{log}"\n'
        'echo "Loading audio file"\n'
        'echo ""\n'
        'echo "bonjour le coach"\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    return log


def test_transcribe_through_fake_binary(fake_voxtype):
    cfg = Config()
    cfg.speech.stt = "voxtype"
    cfg.speech.stt_language = "fr"
    cfg.speech.voxtype_model = "large-v3-turbo"
    assert voxtype_available()
    assert transcribe(b"RIFFfake", cfg) == "bonjour le coach"
    args = fake_voxtype.read_text().strip().split("\n")
    assert args[:5] == ["--quiet", "--language", "fr", "--model", "large-v3-turbo"]
    assert args[5] == "transcribe" and args[6].endswith(".wav")


def test_missing_binary_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    cfg = Config()
    cfg.speech.stt = "voxtype"
    with pytest.raises(STTError, match="voxtype_not_installed"):
        transcribe(b"RIFFfake", cfg)
