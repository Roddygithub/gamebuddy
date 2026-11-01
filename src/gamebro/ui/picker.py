"""Game window picker."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout

from gamebro.capture import CaptureBackend, WindowInfo
from gamebro.i18n import Translator


class WindowPicker(QDialog):
    def __init__(self, backend: CaptureBackend, tr: Translator, own_class: str = "gamebro", parent=None):
        super().__init__(parent)
        self.backend = backend
        self.tr = tr
        self.own_class = own_class
        self.selected: WindowInfo | None = None
        self.setWindowTitle(tr("pick_window"))
        self.resize(460, 380)
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self._accept())
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        refresh = QPushButton("↻")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh)
        cancel = QPushButton(tr("cancel"))
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        ok = QPushButton(tr("save"))
        ok.clicked.connect(self._accept)
        row.addWidget(refresh)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        try:
            windows = self.backend.list_windows()
        except Exception as exc:  # noqa: BLE001
            item = QListWidgetItem(self.tr("error_generic", error=str(exc)))
            item.setFlags(item.flags() & ~item.flags().ItemIsSelectable)
            self.list.addItem(item)
            return
        for w in windows:
            if w.app_id.lower() == self.own_class:
                continue
            item = QListWidgetItem(w.label)
            item.setData(0x0100, w)  # Qt.UserRole
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _accept(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.selected = item.data(0x0100)
        if self.selected is not None:
            self.accept()
