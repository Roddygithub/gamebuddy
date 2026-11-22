"""Foreign text, safe to print on a terminal.

Model replies, window titles, dataset labels and provider errors all reach the
console. ESC and friends turn printed text into terminal commands (cursor
moves, screen clears, title changes), so they are stripped at the display
boundary — never where the text is stored, compared or replayed.
"""

from __future__ import annotations

import re

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


def display_text(value) -> str:
    """``value`` as text that cannot drive the terminal that prints it."""
    return _CONTROL.sub("", str(value))
