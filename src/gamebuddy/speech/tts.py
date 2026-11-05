"""Text to speech: OpenAI, piper or espeak-ng. Returns (audio bytes, format)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

from gamebuddy.config import Config


class TTSError(RuntimeError):
    pass


_MD_RE = re.compile(r"[*_`#>\[\]()|]|https?://\S+")


def speakable(text: str, limit: int = 600) -> str:
    """Strip markdown and URLs so the voice doesn't read symbols aloud."""
    text = _MD_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def synthesize(text: str, cfg: Config, language: str = "en") -> tuple[bytes, str]:
    engine = cfg.speech.tts
    text = speakable(text)
    if engine == "none" or not text:
        return b"", "wav"
    if engine == "openai":
        return _openai(text, cfg), "wav"
    if engine == "piper":
        return _piper(text, cfg), "wav"
    if engine == "espeak":
        return _espeak(text, language), "wav"
    raise TTSError(f"unknown TTS engine: {engine}")


def _openai(text: str, cfg: Config) -> bytes:
    from openai import OpenAI

    key = cfg.openai_key()
    if not key:
        raise TTSError("OPENAI_API_KEY missing for OpenAI speech")
    client = OpenAI(api_key=key, timeout=60)
    resp = client.audio.speech.create(
        model=cfg.speech.tts_model, voice=cfg.speech.tts_voice, input=text, response_format="wav"
    )
    return resp.content


def _piper(text: str, cfg: Config) -> bytes:
    # Prefer the package in GameBuddy's venv, which need not be on the desktop PATH.
    binary = [sys.executable, "-m", "piper"] if find_spec("piper") is not None else [shutil.which("piper")]
    if binary[0] is None:
        raise TTSError("piper not found")
    if not cfg.speech.piper_model:
        raise TTSError("speech.piper_model is not set")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        path = Path(fh.name)
    try:
        proc = subprocess.run(
            [*binary, "--model", cfg.speech.piper_model, "--output_file", str(path)],
            input=text.encode(),
            capture_output=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            raise TTSError(proc.stderr.decode(errors="replace")[:200])
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


_ESPEAK_LANG = {"fr": "fr", "en": "en", "de": "de", "es": "es", "it": "it", "pt-BR": "pt-br", "pt-PT": "pt"}


def _espeak(text: str, language: str) -> bytes:
    binary = "espeak-ng" if shutil.which("espeak-ng") else "espeak"
    if not shutil.which(binary):
        raise TTSError("espeak-ng not found")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        path = Path(fh.name)
    try:
        subprocess.run(
            [binary, "-v", _ESPEAK_LANG.get(language, "en"), "-w", str(path)],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=60,
            check=True,
        )
        return path.read_bytes()
    except subprocess.CalledProcessError as exc:
        raise TTSError(exc.stderr.decode(errors="replace")[:200]) from exc
    finally:
        path.unlink(missing_ok=True)
