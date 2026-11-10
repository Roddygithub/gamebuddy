"""Microphone capture: push-to-talk recording and hands-free (VAD) listening."""

from __future__ import annotations

import io
import logging
import threading
import time
import wave
from collections.abc import Callable

import numpy as np

log = logging.getLogger(__name__)


class AudioUnavailable(RuntimeError):
    pass


def _sd():
    try:
        import sounddevice as sd
    except Exception as exc:  # noqa: BLE001 - portaudio missing
        raise AudioUnavailable(str(exc)) from exc
    return sd


def _device(name: str, kind: str):
    if not name:
        return None
    if name.isdigit():
        return int(name)
    sd = _sd()
    for idx, dev in enumerate(sd.query_devices()):
        if name.lower() in dev["name"].lower() and dev[f"max_{kind}_channels"] > 0:
            return idx
    return None


def pcm_to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    pcm = np.clip(samples, -1.0, 1.0)
    data = (pcm * 32767).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data)
    return buf.getvalue()


def rms(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(block, dtype=np.float64))))


class Recorder:
    """Push-to-talk: start(), then stop() returns WAV bytes (or b'' if too short)."""

    def __init__(
        self, sample_rate: int = 16000, device: str = "", on_level: Callable[[float], None] | None = None
    ):
        self.sample_rate = sample_rate
        self.device = device
        self.on_level = on_level
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        self.started_at = 0.0

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        sd = _sd()
        self._chunks = []

        def callback(indata, _frames, _time, status):  # noqa: ANN001
            if status:
                log.debug("audio status: %s", status)
            mono = indata[:, 0].copy()
            with self._lock:
                self._chunks.append(mono)
            if self.on_level:
                self.on_level(rms(mono))

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=_device(self.device, "input"),
            callback=callback,
            blocksize=int(self.sample_rate * 0.03),
        )
        try:
            self._stream.start()
        except Exception:
            self._stream.close()
            self._stream = None
            raise
        self.started_at = time.time()

    def stop(self) -> bytes:
        if self._stream is None:
            return b""
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
        with self._lock:
            audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
            self._chunks = []
        if audio.size < self.sample_rate * 0.3:  # < 300 ms: ignore accidental taps
            return b""
        return pcm_to_wav(audio, self.sample_rate)


class HandsFreeListener:
    """Energy-based VAD: emits complete utterances as WAV while enabled."""

    def __init__(
        self,
        on_utterance: Callable[[bytes], None],
        sample_rate: int = 16000,
        device: str = "",
        threshold: float = 0.015,
        silence_ms: int = 900,
        max_utterance_s: int = 30,
        idle_sleep_s: int = 120,
        on_level: Callable[[float], None] | None = None,
        on_sleep: Callable[[], None] | None = None,
    ):
        self.on_utterance = on_utterance
        self.sample_rate = sample_rate
        self.device = device
        self.threshold = threshold
        self.silence_ms = silence_ms
        self.max_utterance_s = max_utterance_s
        self.idle_sleep_s = idle_sleep_s
        self.on_level = on_level
        self.on_sleep = on_sleep
        # One utterance at a time: Kin answers one question at a time anyway, so
        # queueing more would only pile up threads and stale audio.
        self._slot = threading.Semaphore(1)
        self.dropped = 0
        self._stream = None
        self._buf: list[np.ndarray] = []
        self._in_speech = False
        self._last_voice = 0.0
        self._speech_start = 0.0
        self._last_activity = time.time()
        self.paused = False  # pause while Buddy speaks to avoid self-triggering

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        sd = _sd()
        self._last_activity = time.time()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=_device(self.device, "input"),
            callback=self._callback,
            blocksize=int(self.sample_rate * 0.03),
        )
        try:
            self._stream.start()
        except Exception:
            self._stream.close()
            self._stream = None
            raise

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            self._buf = []
            self._in_speech = False

    def _deliver(self, wav: bytes) -> None:
        try:
            self.on_utterance(wav)
        finally:
            self._slot.release()

    def _callback(self, indata, _frames, _time, _status):  # noqa: ANN001
        mono = indata[:, 0].copy()
        level = rms(mono)
        if self.on_level:
            self.on_level(level)
        if self.paused:
            return
        now = time.time()
        voiced = level >= self.threshold
        if voiced:
            self._last_voice = now
            self._last_activity = now
            if not self._in_speech:
                self._in_speech = True
                self._speech_start = now
                self._buf = []
        if self._in_speech:
            self._buf.append(mono)
            too_long = now - self._speech_start > self.max_utterance_s
            silent = (now - self._last_voice) * 1000 > self.silence_ms
            if silent or too_long:
                audio = np.concatenate(self._buf)
                self._buf = []
                self._in_speech = False
                if audio.size >= self.sample_rate * 0.4:
                    wav = pcm_to_wav(audio, self.sample_rate)
                    if self._slot.acquire(blocking=False):
                        threading.Thread(target=self._deliver, args=(wav,), daemon=True).start()
                    else:
                        self.dropped += 1  # answered late is worse than not at all
        elif self.idle_sleep_s and now - self._last_activity > self.idle_sleep_s:
            self._last_activity = now
            if self.on_sleep:
                threading.Thread(target=self.on_sleep, daemon=True).start()
