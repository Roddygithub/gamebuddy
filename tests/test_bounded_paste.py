"""A paste into any GameBuddy field is truncated, not ingested whole."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from gamebuddy.ui.inputs import PASTE_LIMIT, BoundedLineEdit


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_paste_is_truncated_and_single_line(qapp):
    QApplication.clipboard().setText("x" * (PASTE_LIMIT * 5) + "\nsecond line")
    field = BoundedLineEdit()
    field._bounded_paste()
    assert len(field.text()) == PASTE_LIMIT
    assert "\n" not in field.text()


def test_ctrl_v_goes_through_the_bounded_path(qapp):
    QApplication.clipboard().setText("y" * (PASTE_LIMIT + 500))
    field = BoundedLineEdit()
    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_V, Qt.ControlModifier, "v")
    field.keyPressEvent(event)
    assert len(field.text()) == PASTE_LIMIT


def test_max_length_is_set_as_a_backstop(qapp):
    field = BoundedLineEdit(limit=12)
    assert field.maxLength() == 12
