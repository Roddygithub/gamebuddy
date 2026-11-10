"""Text fields that never ingest an unbounded clipboard payload."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QClipboard, QKeySequence
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QWidget

PASTE_LIMIT = 2000  # characters accepted from one paste
PASTE_TIMEOUT = 0.2  # seconds to wait for a clipboard transfer

# Admission: at most one clipboard reader in flight at a time, across all fields.
_PASTE_ADMISSION = threading.Semaphore(1)


class BoundedLineEdit(QLineEdit):
    """A one-line field with a hard length, bounded on every paste route.

    Qt's own paste reads the whole clipboard before inserting it, so a huge or
    streaming clipboard owner can block the UI. Every route that can trigger a
    paste (keyboard shortcut, context menu, middle-click, drag-drop) is
    intercepted here and routed through `_bounded_paste`, which reads the
    clipboard in a separate daemon thread and rejects the reply if it is late
    or oversized. A single admission slot prevents accumulated readers.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None, limit: int = PASTE_LIMIT):
        super().__init__(text, parent)
        self._limit = limit
        self.setMaxLength(limit)
        self._paste_cancel = threading.Event()

    def _read_clipboard(self, selection: bool) -> str | None:
        try:
            mode = QClipboard.Selection if selection else QClipboard.Clipboard
            md = QApplication.clipboard().mimeData(mode)
            if md is not None and md.hasText():
                return md.text()
        except Exception:
            return None
        return None

    def _bounded_paste(self, selection: bool = False) -> None:
        if not _PASTE_ADMISSION.acquire(blocking=False):
            return  # admission: another reader in flight; reject
        self._paste_cancel.clear()
        holder = {"text": None, "done": False}

        def worker() -> None:
            try:
                if self._paste_cancel.is_set():
                    return
                holder["text"] = self._read_clipboard(selection)
            finally:
                holder["done"] = True
                _PASTE_ADMISSION.release()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        deadline = time.monotonic() + PASTE_TIMEOUT

        while not holder["done"] and time.monotonic() < deadline:
            thread.join(0.005)
        if not holder["done"]:
            self._paste_cancel.set()  # best-effort cancel; worker is daemon
            return  # late: reject
        text = holder["text"]
        if not text or len(text) > self._limit:
            return  # empty / oversized: reject
        text = text.replace("\n", " ").replace("\r", " ").strip()
        if text:
            try:
                self.insert(text[: self._limit])
            except RuntimeError:
                pass

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
        # Prevent Qt's native middle-button Selection paste.
        if event.button() == Qt.MiddleButton:
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        # Build the menu ourselves so construction never reads the clipboard.
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
