"""Speech to text: OpenAI API, voxtype (Omarchy), faster-whisper (local) or whisper.cpp CLI."""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from gamebuddy.config import Config


class STTError(RuntimeError):
    pass


_local_model = None


def transcribe(wav: bytes, cfg: Config) -> str:
    engine = cfg.speech.stt
    if engine == "none" or not wav:
        return ""
    if engine == "openai":
        return _openai(wav, cfg)
    if engine == "faster_whisper":
        return _faster_whisper(wav, cfg)
    if engine == "whispercpp":
        return _whispercpp(wav, cfg)
    if engine == "voxtype":
        return _voxtype(wav, cfg)
    raise STTError(f"unknown STT engine: {engine}")


def _openai(wav: bytes, cfg: Config) -> str:
    from openai import OpenAI

    key = cfg.openai_key()
    if not key:
        raise STTError("OPENAI_API_KEY missing for OpenAI transcription")
    client = OpenAI(api_key=key, timeout=60)
    kwargs = {"model": cfg.speech.stt_model, "file": ("speech.wav", io.BytesIO(wav), "audio/wav")}
    if cfg.speech.stt_language:
        kwargs["language"] = cfg.speech.stt_language
    result = client.audio.transcriptions.create(**kwargs)
    return (getattr(result, "text", "") or "").strip()


def _faster_whisper(wav: bytes, cfg: Config) -> str:
    global _local_model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise STTError("pip install 'gamebuddy[local]' for faster-whisper") from exc
    if _local_model is None:
        size = cfg.speech.stt_model if cfg.speech.stt_model not in ("", "whisper-1") else "small"
        _local_model = WhisperModel(size, device="auto", compute_type="int8")
    import numpy as np

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        fh.write(wav)
        path = fh.name
    try:
        segments, _info = _local_model.transcribe(
            path, language=cfg.speech.stt_language or None, vad_filter=True, beam_size=1
        )
        return " ".join(s.text.strip() for s in segments).strip()
    finally:
        Path(path).unlink(missing_ok=True)
        del np


def voxtype_available(binary: str = "voxtype") -> bool:
    """True when Omarchy's voxtype CLI is on PATH."""
    return shutil.which(binary) is not None


def parse_voxtype_output(stdout: str) -> str:
    """`voxtype transcribe` prints progress lines, then a blank line and the transcript."""
    lines = stdout.splitlines()
    if any(line.strip().startswith("No speech detected") for line in lines):
        return ""
    blanks = [i for i, line in enumerate(lines) if not line.strip()]
    tail = lines[blanks[-1] + 1 :] if blanks else lines[-1:]
    return " ".join(line.strip() for line in tail if line.strip()).strip()


def _voxtype(wav: bytes, cfg: Config) -> str:
    """Reuse voxtype's engine, model and GPU build (ships with Omarchy: Install > AI > Dictation)."""
    binary = cfg.speech.voxtype_binary
    if not voxtype_available(binary):
        raise STTError("voxtype_not_installed")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        fh.write(wav)
        path = fh.name
    try:
        cmd = [binary, "--quiet"]
        if cfg.speech.stt_language:
            cmd += ["--language", cfg.speech.stt_language]
        if cfg.speech.voxtype_model:
            cmd += ["--model", cfg.speech.voxtype_model]
        cmd += ["transcribe", path]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0:
            err = (proc.stderr.strip() or proc.stdout.strip())[-300:]
            if "model" in err.lower() and ("not found" in err.lower() or "download" in err.lower()):
                raise STTError("voxtype_no_model")
            raise STTError(f"voxtype_failed: {err}")
        return parse_voxtype_output(proc.stdout)
    except subprocess.TimeoutExpired as exc:
        raise STTError("voxtype_timeout") from exc
    finally:
        Path(path).unlink(missing_ok=True)


def _whispercpp(wav: bytes, cfg: Config) -> str:
    if not cfg.speech.whispercpp_model:
        raise STTError("speech.whispercpp_model is not set")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        fh.write(wav)
        path = fh.name
    try:
        cmd = [
            cfg.speech.whispercpp_binary,
            "-m",
            cfg.speech.whispercpp_model,
            "-f",
            path,
            "-nt",
            "-np",
            "-l",
            cfg.speech.stt_language or "auto",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0:
            raise STTError(proc.stderr.strip()[:200])
        return " ".join(line.strip() for line in proc.stdout.splitlines() if line.strip())
    except FileNotFoundError as exc:
        raise STTError(f"{cfg.speech.whispercpp_binary} not found") from exc
    finally:
        Path(path).unlink(missing_ok=True)
