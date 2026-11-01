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
