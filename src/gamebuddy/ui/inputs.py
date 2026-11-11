"""Text fields that never ingest an unbounded clipboard payload."""

from __future__ import annotations

import select
import shutil
import subprocess
import threading
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QClipboard, QKeySequence
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QWidget

PASTE_LIMIT = 2000  # characters accepted from one paste
PASTE_TIMEOUT = 0.2  # seconds to wait for a clipboard transfer
BYTE_CAP_FACTOR = 4  # bytes per char (UTF-8 worst case)

_PASTE_ADMISSION = threading.Semaphore(1)
_WL_PASTE = shutil.which("wl-paste")


def _read_clipboard_wayland(selection: bool, limit: int, timeout: float) -> str | None:
    """Bounded, cancellable clipboard read via wl-paste."""
    if _WL_PASTE is None:
        return None
    cmd = [_WL_PASTE, "--no-newline"]
    if selection:
        cmd.append("--primary")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return None
    cap_bytes = limit * BYTE_CAP_FACTOR + 1
    chunks: list[bytes] = []
    total = 0
    oversized = False
    deadline = time.monotonic() + timeout
    try:
        while total < cap_bytes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 0.05))
            if ready:
                chunk = proc.stdout.read(min(4096, cap_bytes - total))
                if not chunk:
                    break  # EOF
                chunks.append(chunk)
                total += len(chunk)
                if total >= cap_bytes:
                    oversized = True
                    break
            else:
                if proc.poll() is not None:
                    chunk = proc.stdout.read(cap_bytes - total)
                    if chunk:
                        chunks.append(chunk)
                        total += len(chunk)
                    break
    except (TimeoutError, OSError):
        oversized = False
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        proc.wait()
        return None  # late: reject
    # terminate if still running
    if proc.poll() is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        proc.wait()
    if oversized:
        return None  # oversized: reject
    data = b"".join(chunks)
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return None
    if len(text) > limit:
        return None
    return text


def _read_clipboard_qt(selection: bool) -> str | None:
    try:
        mode = QClipboard.Selection if selection else QClipboard.Clipboard
        md = QApplication.clipboard().mimeData(mode)
        if md is not None and md.hasText():
            return md.text()
    except Exception:
        return None
    return None


class BoundedLineEdit(QLineEdit):
    """A one-line field with a hard length, bounded on every paste route."""

    def __init__(self, text: str = "", parent: QWidget | None = None, limit: int = PASTE_LIMIT):
        super().__init__(text, parent)
        self._limit = limit
        self.setMaxLength(limit)

    def _read_clipboard(self, selection: bool) -> str | None:
        text = _read_clipboard_wayland(selection, self._limit, PASTE_TIMEOUT)
        if text:
            return text
        # Fallback (Qt-seeded clipboard in tests / non-Wayland): best-effort.
        qt_text = _read_clipboard_qt(selection)
        if qt_text:
            if len(qt_text) > self._limit:
                return None
            return qt_text
        if text == "":
            return ""
        return None

    def _bounded_paste(self, selection: bool = False) -> None:
        if not _PASTE_ADMISSION.acquire(blocking=False):
            return
        try:
            text = self._read_clipboard(selection)
            if not text:
                return
            text = text.replace("\n", " ").replace("\r", " ").strip()
            if text:
                try:
                    self.insert(text[: self._limit])
                except RuntimeError:
                    pass
        finally:
            _PASTE_ADMISSION.release()

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
            text = md.text()
            if text and len(text) <= self._limit:
                text = text.replace("\n", " ").replace("\r", " ").strip()
                if text:
                    try:
                        self.insert(text[: self._limit])
                    except RuntimeError:
                        pass
            event.accept()
            return
        super().dropEvent(event)

    def insertFromMimeData(self, source) -> None:  # noqa: N802
        cb = QApplication.clipboard()
        if source is not None and source is cb.mimeData():
            self._bounded_paste(False)
            return
        if source is not None and source.hasText():
            text = source.text()
            if text and len(text) <= self._limit:
                text = text.replace("\n", " ").replace("\r", " ").strip()
                if text:
                    try:
                        self.insert(text[: self._limit])
                    except RuntimeError:
                        pass
