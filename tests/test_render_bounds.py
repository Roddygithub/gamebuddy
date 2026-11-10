"""Nothing the model or the user types reaches Qt unbounded."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gamebuddy.i18n import Translator
from gamebuddy.ui.widget import BUBBLE_LIMIT, FEED_BUBBLES, PIN_LINES, BuddyWidget, md_to_html


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def widget(qapp):
    w = BuddyWidget(Translator("en"), "Buddy", "ALT, V", 420, 640, mode="panel", compact_orb=False)
    yield w
    w.close()


def test_markdown_is_capped_before_qt_parses_it():
    html = md_to_html("word " * (BUBBLE_LIMIT * 2))
    assert len(html) < BUBBLE_LIMIT * 4  # budget applied, not the full input


def test_only_web_links_survive():
    html = md_to_html("[x](javascript:alert(1)) and [ok](https://example.com)")
    assert "javascript:" not in html
    assert "https://example.com" in html


def test_typed_text_stays_literal(widget):
    label = widget.add_bubble("<b>not bold</b> 500 < 600", "user")
    assert label.textFormat() == Qt.PlainText
    assert label.text() == "<b>not bold</b> 500 < 600"


def test_error_text_stays_literal(widget):
    label = widget.add_bubble("`code` <not a tag>", "error")
    assert label.textFormat() == Qt.PlainText


def test_the_feed_keeps_a_bounded_number_of_bubbles(widget):
    for i in range(FEED_BUBBLES + 25):
        widget.add_bubble(f"advice {i}", "bro")
    assert widget.feed_layout.count() - 1 == FEED_BUBBLES


def test_pinned_content_is_row_and_size_bounded(widget):
    widget.show_pin("Title", "\n".join(f"line {i}" for i in range(PIN_LINES + 300)))
    assert widget.pin_body.toPlainText().count("\n") <= PIN_LINES + 2
