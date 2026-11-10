"""Text fields that never ingest an unbounded clipboard payload."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

PASTE_LIMIT = 2000  # characters accepted from one paste


class BoundedLineEdit(QLineEdit):
    """A one-line field with a hard length, bounded on the paste path.

    Qt's own paste reads the whole clipboard before inserting it, so a huge or
    streaming clipboard owner can block the UI. The keyboard path is handled
    here: the text is taken once and truncated. ponytail: the context-menu and
    middle-click entries still go through Qt, where `setMaxLength` only trims
    after retrieval; they are bounded in length, not in transfer cost.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None, limit: int = PASTE_LIMIT):
        super().__init__(text, parent)
        self._limit = limit
        self.setMaxLength(limit)

    def _bounded_paste(self) -> None:
        data = QApplication.clipboard().mimeData()
        if data is None or not data.hasText():
            return
        text = data.text()[: self._limit].replace("\n", " ").replace("\r", " ").strip()
        if text:
            self.insert(text)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        is_paste = event.matches(QKeySequence.Paste) or (
            event.key() == Qt.Key_Insert and bool(event.modifiers() & Qt.ShiftModifier)
        )
        if is_paste:
            self._bounded_paste()
            return
        super().keyPressEvent(event)
