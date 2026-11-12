"""A paste into any GameBuddy field is bounded, not ingested whole.

The field must never fall back to Qt's ``mimeData().text()`` for a foreign
offer: that call retrieves the whole transfer. These tests use a fake
``wl-paste`` to act as a slow or oversized foreign clipboard owner.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from gamebuddy.ui import inputs
from gamebuddy.ui.inputs import PASTE_LIMIT, BoundedLineEdit


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def foreign(monkeypatch):
    """Make every Qt clipboard read look like a foreign offer."""

    def set_foreign():
        monkeypatch.setattr(inputs, "_owns_clipboard", lambda selection: False)

    return set_foreign


@pytest.fixture
def own(monkeypatch):
    """The offscreen platform does not report clipboard ownership; assert it."""

    def set_own():
        monkeypatch.setattr(inputs, "_owns_clipboard", lambda selection: True)

    return set_own


@pytest.fixture
def fake_wl_paste(tmp_path, monkeypatch):
    def make(script: str) -> None:
        path = tmp_path / "wl-paste"
        path.write_text("#!/bin/sh\n" + script, encoding="utf-8")
        path.chmod(0o755)
        monkeypatch.setattr(inputs, "_WL_PASTE", str(path))

    return make


def settle(timeout: float = 3.0) -> None:
    """Run the event loop until the background paste reader has finished."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if inputs._PASTE_ADMISSION.acquire(blocking=False):
            inputs._PASTE_ADMISSION.release()
            QApplication.processEvents()
            return
        time.sleep(0.01)
    raise AssertionError("paste reader did not finish in time")


def paste(field: BoundedLineEdit, selection: bool = False) -> None:
    field._bounded_paste(selection)
    settle()


def test_oversized_paste_is_rejected(qapp, own):
    own()
    QApplication.clipboard().setText("x" * (PASTE_LIMIT * 5) + "\nsecond line")
    field = BoundedLineEdit()
    paste(field)
    assert field.text() == ""


def test_ctrl_v_goes_through_the_bounded_path(qapp, own):
    own()
    QApplication.clipboard().setText("y" * (PASTE_LIMIT + 500))
    field = BoundedLineEdit()
    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_V, Qt.ControlModifier, "v")
    field.keyPressEvent(event)
    settle()
    assert field.text() == ""


def test_within_limit_paste_is_inserted(qapp, own):
    own()
    payload = "z" * 100
    QApplication.clipboard().setText(payload)
    field = BoundedLineEdit()
    paste(field)
    assert field.text() == payload


def test_max_length_is_set_as_a_backstop(qapp):
    field = BoundedLineEdit(limit=12)
    assert field.maxLength() == 12


def test_oversized_foreign_offer_is_refused(qapp, fake_wl_paste, foreign):
    fake_wl_paste("head -c 200000 /dev/zero | tr '\\0' 'A'\nwhile :; do sleep 1; done\n")
    foreign()
    assert inputs.read_clipboard(False, PASTE_LIMIT, 0.5) is None


def test_slow_offer_holding_the_pipe_open_is_refused(qapp, fake_wl_paste, foreign):
    fake_wl_paste("printf 'partial'\nsleep 5\n")
    foreign()
    started = time.monotonic()
    assert inputs.read_clipboard(False, PASTE_LIMIT, 0.2) is None
    assert time.monotonic() - started < 1.5


def test_refused_transfer_never_falls_back_to_the_qt_read(qapp, fake_wl_paste, foreign):
    fake_wl_paste("exit 1\n")
    QApplication.clipboard().setText("small enough to be accepted")
    foreign()
    assert inputs.read_clipboard(False, PASTE_LIMIT, 0.2) is None


def test_own_clipboard_is_read_through_qt_when_the_helper_fails(qapp, fake_wl_paste, own):
    fake_wl_paste("exit 1\n")
    own()
    QApplication.clipboard().setText("local payload")
    assert inputs.read_clipboard(False, PASTE_LIMIT, 0.2) == "local payload"


def test_paste_returns_before_the_reader_finishes(qapp, monkeypatch):
    def slow_read(selection, limit, timeout):
        time.sleep(0.3)
        return "late payload"

    monkeypatch.setattr(inputs, "_read_clipboard_wayland", slow_read)
    field = BoundedLineEdit()
    started = time.monotonic()
    field._bounded_paste()
    assert time.monotonic() - started < 0.15  # the GUI thread is not waiting
    settle()
    assert field.text() == "late payload"
