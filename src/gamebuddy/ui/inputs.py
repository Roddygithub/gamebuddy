"""Text fields that never ingest an unbounded clipboard payload."""

from __future__ import annotations

import os
import select
import shutil
import subprocess
import threading
import time

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QClipboard, QKeySequence
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QWidget

PASTE_LIMIT = 2000  # characters accepted from one paste
PASTE_TIMEOUT = 0.2  # seconds allowed for the whole clipboard transfer
BYTE_CAP_FACTOR = 4  # bytes per char (UTF-8 worst case)

_PASTE_ADMISSION = threading.Semaphore(1)
_WL_PASTE = shutil.which("wl-paste")


def _owns_clipboard(selection: bool) -> bool:
    """True when this process is the clipboard owner: its data is local memory."""
    clipboard = QApplication.clipboard()
    try:
        return clipboard.ownsSelection() if selection else clipboard.ownsClipboard()
    except Exception:
        return False


def _read_clipboard_wayland(selection: bool, limit: int, timeout: float) -> str | None:
    """Bounded, cancellable clipboard read via wl-paste.

    ``None`` means the transfer was refused (failed, oversized or late); the
    caller must not retry it through a path that retrieves the whole payload.
    """
    if _WL_PASTE is None:
        return None
    cmd = [_WL_PASTE, "--no-newline"]
    if selection:
        cmd.append("--primary")
    try:
        # Unbuffered: every read below is one syscall on what is already there.
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    except OSError:
        return None
    assert proc.stdout is not None
    fd = proc.stdout.fileno()
    cap_bytes = limit * BYTE_CAP_FACTOR + 1
    chunks: list[bytes] = []
    total = 0
    refused = False
    deadline = time.monotonic() + timeout
    try:
        while total < cap_bytes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.05))
            if not ready:
                if proc.poll() is not None:
                    break  # exited and nothing more to read
                continue
            # Readiness only promises *some* bytes: one raw read, never a
            # buffered read that would wait for the full request.
            chunk = os.read(fd, min(4096, cap_bytes - total))
            if not chunk:
                break  # EOF
            chunks.append(chunk)
            total += len(chunk)
            if total >= cap_bytes:
                refused = True  # oversized: never truncated, refused
    except (TimeoutError, OSError):
        refused = True  # late or broken transfer: refuse, do not insert a prefix
    finally:
        if proc.poll() is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        proc.wait()
    if refused or proc.returncode:
        return None  # wl-paste failed: refuse rather than paste a partial offer
    return b"".join(chunks).decode("utf-8", errors="replace")


def _read_clipboard_qt(selection: bool, limit: int) -> str | None:
    """Read the clipboard through Qt; only valid for our own (local) data."""
    try:
        mode = QClipboard.Selection if selection else QClipboard.Clipboard
        md = QApplication.clipboard().mimeData(mode)
    except Exception:
        return None
    if md is None or not md.hasText():
        return None
    text = md.text()
    return None if len(text) > limit else text


def read_clipboard(selection: bool, limit: int = PASTE_LIMIT, timeout: float = PASTE_TIMEOUT) -> str | None:
    """Bounded clipboard read. ``None`` means: refuse this paste.

    Qt's ``mimeData().text()`` retrieves a foreign transfer whole, so it is
    only used when this process owns the clipboard (local memory). A foreign
    offer goes through the bounded helper, and a failed, late or oversized
    offer stays refused. Qt calls must happen on the GUI thread.
    """
    if _owns_clipboard(selection):
        return _read_clipboard_qt(selection, limit)
    return _read_clipboard_wayland(selection, limit, timeout)


class _PasteSignal(QObject):
    ready = Signal(str)


def _one_line(text: str, limit: int) -> str:
    return text.replace("\n", " ").replace("\r", " ").strip()[:limit]


class BoundedLineEdit(QLineEdit):
    """A one-line field with a hard length, bounded on every paste route."""

    def __init__(self, text: str = "", parent: QWidget | None = None, limit: int = PASTE_LIMIT):
        super().__init__(text, parent)
        self._limit = limit
        self.setMaxLength(limit)
        self._paste = _PasteSignal(self)
        self._paste.ready.connect(self._apply_pasted_text, Qt.QueuedConnection)

    def _read_clipboard(self, selection: bool) -> str | None:
        return read_clipboard(selection, self._limit, PASTE_TIMEOUT)

    def _bounded_paste(self, selection: bool = False) -> None:
        """Read a foreign offer off the GUI thread; own data is already local."""
        if not _PASTE_ADMISSION.acquire(blocking=False):
            return  # one paste in flight; a burst must not start more readers
        if _owns_clipboard(selection):
            try:
                self._apply_pasted_text(_read_clipboard_qt(selection, self._limit) or "")
            finally:
                _PASTE_ADMISSION.release()
            return
        signal, limit = self._paste, self._limit

        def worker() -> None:
            try:
                text = _read_clipboard_wayland(selection, limit, PASTE_TIMEOUT) or ""
                signal.ready.emit(text)
            except Exception:
                pass  # a refused paste inserts nothing
            finally:
                _PASTE_ADMISSION.release()

        threading.Thread(target=worker, name="gamebuddy-paste", daemon=True).start()

    def _apply_pasted_text(self, text: str) -> None:
        text = _one_line(text or "", self._limit)
        if not text:
            return
        try:
            self.insert(text)
        except RuntimeError:
            pass  # the field closed while the reader was finishing

    def keyPressEvent(self, event) -> None:  # noqa: N802
        is_paste = event.matches(QKeySequence.Paste) or (
            event.key() == Qt.Key_Insert and bool(event.modifiers() & Qt.ShiftModifier)
        )
        if is_paste:
            self._bounded_paste(False)
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MiddleButton:
            self._bounded_paste(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MiddleButton:
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        cut = QAction("Cut", self)
        cut.triggered.connect(self.cut)
        menu.addAction(cut)
        copy = QAction("Copy", self)
        copy.triggered.connect(self.copy)
        menu.addAction(copy)
        paste = QAction("Paste", self)
        paste.triggered.connect(lambda: self._bounded_paste(False))
        menu.addAction(paste)
        select_all = QAction("Select All", self)
        select_all.triggered.connect(self.selectAll)
        menu.addAction(select_all)
        menu.exec(event.globalPos())
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802
        md = event.mimeData()
        if md is not None and md.hasText():
            # Refusing before the payload is retrieved is the only bound that
            # works: Qt reads a dropped text offer whole.
            event.setDropAction(Qt.IgnoreAction)
            event.accept()
            return
        super().dropEvent(event)
