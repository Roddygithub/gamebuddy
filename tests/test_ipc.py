import tempfile
import time
from pathlib import Path

from gamebuddy.ipc import IPCServer, is_running, send_command


def test_roundtrip_and_stale_socket(tmp_path):
    path = Path(tempfile.mkdtemp(prefix="gb", dir="/tmp")) / "s.sock"
    seen = []

    def handler(req):
        seen.append(req)
        return {"ok": True, "echo": req.get("cmd")}

    srv = IPCServer(handler, path)
    srv.start()
    try:
        assert is_running(path)
        assert send_command({"cmd": "ptt", "action": "start"}, path)["echo"] == "ptt"
        assert seen[-1]["action"] == "start"
    finally:
        srv.stop()
    assert not is_running(path)
    # stale file left behind → next server reclaims it
    path.touch()
    srv2 = IPCServer(handler, path)
    srv2.start()
    try:
        assert send_command({"cmd": "x"}, path)["ok"]
    finally:
        srv2.stop()


def test_second_instance_refused(tmp_path):
    path = Path(tempfile.mkdtemp(prefix="gb", dir="/tmp")) / "s.sock"
    srv = IPCServer(lambda r: {"ok": True}, path)
    srv.start()
    try:
        import pytest

        with pytest.raises(RuntimeError):
            IPCServer(lambda r: {"ok": True}, path).start()
    finally:
        srv.stop()


def test_bad_json(tmp_path):
    import socket

    path = Path(tempfile.mkdtemp(prefix="gb", dir="/tmp")) / "s.sock"
    srv = IPCServer(lambda r: {"ok": True}, path)
    srv.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(str(path))
            s.sendall(b"not json\n")
            time.sleep(0.1)
            assert b'"ok": false' in s.recv(1024)
    finally:
        srv.stop()


def test_invalid_requests_do_not_disconnect_client():
    import json
    import socket

    path = Path(tempfile.mkdtemp(prefix="gb", dir="/tmp")) / "s.sock"
    srv = IPCServer(lambda r: {"ok": True}, path)
    srv.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(str(path))
            with s.makefile("rb") as reader:
                for payload in (b"[]", b"null", b"42", b'"hello"', b"\xff"):
                    s.sendall(payload + b"\n")
                    assert json.loads(reader.readline())["ok"] is False
                s.sendall(b'{"cmd": "ping"}\n')
                assert json.loads(reader.readline())["ok"] is True
    finally:
        srv.stop()


def test_slow_subscriber_does_not_hold_shutdown_lock(tmp_path):
    import threading

    entered = threading.Event()
    stopped = threading.Event()

    class SlowSubscriber:
        def sendall(self, _line):
            entered.set()
            assert stopped.wait(2)
            raise OSError("closed")

        def shutdown(self, _how):
            stopped.set()

        def close(self):
            stopped.set()

    srv = IPCServer(lambda _request: {"ok": True}, tmp_path / "ipc.sock")
    srv._subscribers.append(SlowSubscriber())
    worker = threading.Thread(target=srv.broadcast, args=("coach",), kwargs={"advice": "test"})
    worker.start()
    assert entered.wait(2)

    srv.stop()
    worker.join(2)

    assert not worker.is_alive()


def test_cancelled_broadcast_stops_before_next_subscriber(tmp_path):
    import threading

    entered = threading.Event()
    release = threading.Event()
    enabled = [True]
    second_received = []

    class SlowSubscriber:
        def sendall(self, _line):
            entered.set()
            assert release.wait(2)

    class FastSubscriber:
        def sendall(self, line):
            second_received.append(line)

    srv = IPCServer(lambda _request: {"ok": True}, tmp_path / "ipc.sock")
    srv._subscribers.extend((SlowSubscriber(), FastSubscriber()))
    worker = threading.Thread(
        target=srv.broadcast,
        args=("coach",),
        kwargs={"should_send": lambda: enabled[0], "advice": "test"},
    )
    worker.start()
    assert entered.wait(2)
    enabled[0] = False
    release.set()
    worker.join(2)

    assert not worker.is_alive()
    assert second_received == []


def test_concurrent_broadcasts_are_serialized_per_subscriber(tmp_path):
    import json
    import threading

    entered = threading.Event()
    release = threading.Event()
    active = [0]
    received = []
    guard = threading.Lock()

    class Subscriber:
        def sendall(self, line):
            with guard:
                active[0] += 1
                assert active[0] == 1
            if b'"first"' in line:
                entered.set()
                assert release.wait(2)
            received.append(line)
            with guard:
                active[0] -= 1

    srv = IPCServer(lambda _request: {"ok": True}, tmp_path / "ipc.sock")
    srv._subscribers.append(Subscriber())
    first = threading.Thread(target=srv.broadcast, args=("first",))
    second = threading.Thread(target=srv.broadcast, args=("second",))
    first.start()
    assert entered.wait(2)
    second.start()
    release.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert [json.loads(line)["event"] for line in received] == ["first", "second"]


def test_subscribe_ack_precedes_any_broadcast(tmp_path):
    import threading

    ack_started = threading.Event()
    release_ack = threading.Event()
    sent = []

    class Subscriber:
        def settimeout(self, _seconds):
            pass

        def recv(self, _size):
            return b'{"cmd":"subscribe"}\n'

        def sendall(self, line):
            if b"subscribed" in line:
                ack_started.set()
                assert release_ack.wait(2)
            sent.append(line)

        def close(self):
            pass

        def shutdown(self, _how):
            pass

    srv = IPCServer(lambda _request: {"ok": True}, tmp_path / "ipc.sock")
    subscriber = Subscriber()
    srv._handle_thread = threading.Thread(target=srv._handle, args=(subscriber,))
    srv._handle_thread.start()
    assert ack_started.wait(2)
    srv.broadcast("coach", advice="early")
    release_ack.set()
    srv._handle_thread.join(2)
    srv.broadcast("coach", advice="after ack")

    assert not srv._handle_thread.is_alive()
    assert sent[0] == b'{"ok": true, "subscribed": true}\n'
    assert b'"after ack"' in sent[1]
    srv.stop()


def test_stopping_rejected_instance_preserves_active_socket():
    import pytest

    path = Path(tempfile.mkdtemp(prefix="gb", dir="/tmp")) / "s.sock"
    srv = IPCServer(lambda r: {"ok": True}, path)
    rejected = IPCServer(lambda r: {"ok": True}, path)
    srv.start()
    try:
        with pytest.raises(RuntimeError):
            rejected.start()
        rejected.stop()
        assert is_running(path)
    finally:
        srv.stop()
