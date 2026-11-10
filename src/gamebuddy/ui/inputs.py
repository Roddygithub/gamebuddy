"""Text fields that never ingest an unbounded clipboard payload."""

from __future__ import annotations

import threading

from PySide6.QtCore import Qt
from PySide6.QtGui import QClipboard, QKeySequence
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

PASTE_LIMIT = 2000  # characters accepted from one paste
PASTE_TIMEOUT = 0.2  # seconds to wait for a clipboard transfer


class BoundedLineEdit(QLineEdit):
    """A one-line field with a hard length, bounded on every paste route.

    Qt's own paste reads the whole clipboard before inserting it, so a huge or
    streaming clipboard owner can block the UI. All paste routes (keyboard
    shortcut, context menu, middle-click and drag-drop) are funnelled through
    `_bounded_paste`, which reads the clipboard in a separate daemon thread and
    rejects the reply if it is late or oversized.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None, limit: int = PASTE_LIMIT):
        super().__init__(text, parent)
        self._limit = limit
        self.setMaxLength(limit)

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
        holder = {"text": None}

        def worker() -> None:
            holder["text"] = self._read_clipboard(selection)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(PASTE_TIMEOUT)
        if thread.is_alive():
            return  # late: reject
        try:
            limit = self._limit
            text = holder["text"]
            if not text or len(text) > limit:
                return  # empty / oversized: reject
            text = text.replace("\n", " ").replace("\r", " ").strip()
            if text:
                self.insert(text[:limit])
        except RuntimeError:
            pass  # edit destroyed: bind completion to original edit

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
        # oversized drag-drop payload: reject
