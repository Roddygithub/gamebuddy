"""Microphone startup failures must release the device and allow a retry."""

from types import SimpleNamespace

import pytest

from gamebuddy.audio import recorder


@pytest.mark.parametrize("kind", ["ptt", "hands_free"])
def test_failed_stream_start_closes_device_and_can_retry(monkeypatch, kind):
    streams = []

    class Stream:
        def __init__(self, **kwargs):
            self.closed = False
            self.fail = not streams
            streams.append(self)

        def start(self):
            if self.fail:
                raise RuntimeError("device unavailable")

        def stop(self):
            pass

        def close(self):
            self.closed = True

    monkeypatch.setattr(recorder, "_sd", lambda: SimpleNamespace(InputStream=Stream))
    mic = recorder.Recorder() if kind == "ptt" else recorder.HandsFreeListener(lambda wav: None)
    with pytest.raises(RuntimeError, match="device unavailable"):
        mic.start()
    assert streams[0].closed
    assert mic._stream is None
    mic.start()
    assert mic._stream is streams[1]
    mic.stop()
    assert streams[1].closed
