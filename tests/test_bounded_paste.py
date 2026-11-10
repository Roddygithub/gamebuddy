"""A paste into any GameBuddy field is bounded, not ingested whole."""

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


def test_oversized_paste_is_rejected(qapp):
    QApplication.clipboard().setText("x" * (PASTE_LIMIT * 5) + "\nsecond line")
    field = BoundedLineEdit()
    field._bounded_paste()
    assert field.text() == ""


def test_ctrl_v_goes_through_the_bounded_path(qapp):
    QApplication.clipboard().setText("y" * (PASTE_LIMIT + 500))
    field = BoundedLineEdit()
    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_V, Qt.ControlModifier, "v")
    field.keyPressEvent(event)
    assert field.text() == ""


def test_within_limit_paste_is_inserted(qapp):
    payload = "z" * 100
    QApplication.clipboard().setText(payload)
    field = BoundedLineEdit()
    field._bounded_paste()
    assert field.text() == payload


def test_max_length_is_set_as_a_backstop(qapp):
    field = BoundedLineEdit(limit=12)
    assert field.maxLength() == 12
