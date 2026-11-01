"""Local IPC over a Unix socket, newline-delimited JSON.

The running widget hosts the server; `gamebuddy ptt start`, Hyprland keybinds,
the Omarchy bar widget or any script talk to it through `send_command`.

Request:  {"cmd": "ptt", "action": "start"}\n
Response: {"ok": true, ...}\n

A client may send {"cmd": "subscribe"} to keep the connection open and receive
events ({"event": "status", ...}) — this is what a future QML panel would use.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gamebuddy.paths import socket_path

Handler = Callable[[dict[str, Any]], dict[str, Any]]
MAX_MESSAGE_BYTES = 1024 * 1024


class IPCServer:
    def __init__(self, handler: Handler, path: Path | None = None):
        self.handler = handler
        self.path = path or socket_path()
        self._sock: socket.socket | None = None
        self._subscribers: list[socket.socket] = []
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._bound = False

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if self._bound:
            raise RuntimeError("IPC server already started")
        self._stop.clear()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            # Stale socket from a previous crash? Probe it first.
            if _probe(self.path):
                raise RuntimeError(f"GameBuddy already running on {self.path}")
            self.path.unlink()
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.path))
        self._bound = True
        os.chmod(self.path, 0o600)
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self._thread = threading.Thread(target=self._serve, name="gamebuddy-ipc", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        with self._lock:
            for s in self._subscribers:
                try:
                    s.close()
                except OSError:
                    pass
            self._subscribers.clear()
        try:
            if self._bound and self.path.exists():
                self.path.unlink()
        except OSError:
            pass
        self._bound = False
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)

    # ---- events ----------------------------------------------------------
    def broadcast(self, event: str, **payload: Any) -> None:
        line = (json.dumps({"event": event, **payload}) + "\n").encode()
        with self._lock:
            dead = []
            for s in self._subscribers:
                try:
                    s.sendall(line)
                except OSError:
                    dead.append(s)
            for s in dead:
                self._subscribers.remove(s)

    # ---- internals -------------------------------------------------------
    def _serve(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        conn.settimeout(5)
        buf = b""
        try:
            while not self._stop.is_set():
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if any(len(line) > MAX_MESSAGE_BYTES for line in buf.split(b"\n")):
                    conn.sendall(b'{"ok": false, "error": "message too large"}\n')
                    break
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        req = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        conn.sendall(b'{"ok": false, "error": "bad json"}\n')
                        continue
                    if not isinstance(req, dict):
                        conn.sendall(b'{"ok": false, "error": "expected JSON object"}\n')
                        continue
                    if req.get("cmd") == "subscribe":
                        # A slow subscriber must not block broadcast (or shutdown) forever.
                        with self._lock:
                            self._subscribers.append(conn)
                        conn.sendall(b'{"ok": true, "subscribed": true}\n')
                        return  # keep socket open for events; owned by subscribers list
                    try:
                        resp = self.handler(req)
                    except Exception as exc:  # noqa: BLE001 - surface to client
                        resp = {"ok": False, "error": str(exc)}
                    conn.sendall((json.dumps(resp) + "\n").encode())
        except (OSError, TimeoutError):
            pass
        finally:
            with self._lock:
                if conn not in self._subscribers:
                    try:
                        conn.close()
                    except OSError:
                        pass


def _probe(path: Path) -> bool:
    try:
        resp = send_command({"cmd": "ping"}, path=path, timeout=0.5)
        return bool(resp.get("ok"))
    except OSError:
        return False


def send_command(request: dict[str, Any], path: Path | None = None, timeout: float = 5.0) -> dict[str, Any]:
    """Send one request to the running widget and return its response."""
    path = path or socket_path()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(path))
        s.sendall((json.dumps(request) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    line = buf.split(b"\n", 1)[0]
    return json.loads(line) if line else {"ok": False, "error": "no response"}


def is_running(path: Path | None = None) -> bool:
    path = path or socket_path()
    return path.exists() and _probe(path)
