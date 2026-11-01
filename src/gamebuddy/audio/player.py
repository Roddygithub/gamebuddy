"""Audio playback for TTS output."""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

_current: dict[str, object] = {"proc": None, "stop": threading.Event()}


def stop() -> None:
    ev = _current["stop"]
    assert isinstance(ev, threading.Event)
    ev.set()
    proc = _current.get("proc")
    if isinstance(proc, subprocess.Popen) and proc.poll() is None:
        proc.terminate()
    try:
        import sounddevice as sd

        sd.stop()
    except Exception:  # noqa: BLE001
        pass


def play(data: bytes, fmt: str = "wav", device: str = "") -> None:
    """Blocking playback. WAV goes through sounddevice; anything else through a CLI player."""
    stop()
    ev = threading.Event()
    _current["stop"] = ev
    if fmt == "wav":
        try:
            _play_wav(data, device)
            return
        except Exception:  # noqa: BLE001 - fall back to CLI
            pass
    _play_cli(data, fmt)


def _play_wav(data: bytes, device: str) -> None:
    import sounddevice as sd

    with wave.open(io.BytesIO(data), "rb") as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[width]
    samples = np.frombuffer(frames, dtype=dtype)
    if channels > 1:
        samples = samples.reshape(-1, channels)
    dev = None
    if device:
        dev = int(device) if device.isdigit() else device
    sd.play(samples, rate, device=dev)
    sd.wait()


def _play_cli(data: bytes, fmt: str) -> None:
    for player in ("pw-play", "paplay", "ffplay", "mpv", "afplay", "aplay"):
        if shutil.which(player):
            break
    else:
        raise RuntimeError("no audio player found (pw-play/paplay/ffplay/mpv)")
    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as fh:
        fh.write(data)
        path = Path(fh.name)
    try:
        if player == "ffplay":
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
        elif player == "mpv":
            cmd = ["mpv", "--no-video", "--really-quiet", str(path)]
        else:
            cmd = [player, str(path)]
        proc = subprocess.Popen(cmd)
        _current["proc"] = proc
        proc.wait()
    finally:
        path.unlink(missing_ok=True)
