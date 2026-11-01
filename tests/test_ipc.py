import tempfile
import time
from pathlib import Path

from gamebro.ipc import IPCServer, is_running, send_command


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
