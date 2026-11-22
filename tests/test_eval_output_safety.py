"""The eval summary prints foreign text as text, never as terminal commands."""

from __future__ import annotations

from gamebuddy.display import display_text
from gamebuddy.eval.run import _print_summary


def test_summary_strips_terminal_control_sequences(tmp_path):
    report = {
        "schema": "gamebuddy-eval/1",
        "dataset": str(tmp_path / "suite"),
        "mode": "replay",
        "provider": "fake",
        "model": "fake-1",
        "cases": [
            {
                "name": "shop\x1b[2J",
                "pass_hat_k": False,
                "runs": [
                    {
                        "advice": "Buy Slark. \x1b[2J\x1b[H",
                        "accepted": True,
                        "reject_reason": "",
                        "latency_s": 1.0,
                        "decision": "ADVISE",
                        "notes": ["provider error: \x1b]0;owned\x07"],
                    }
                ],
            }
        ],
        "summary": {
            "cases": 1,
            "runs": 1,
            "pass_1": 0.0,
            "pass_at_1": 0.0,
            "pass_hat_1": 0.0,
            "measures": {},
        },
    }
    lines: list[str] = []
    _print_summary(report, tmp_path / "report.json", lines.append)
    assert lines
    assert "Buy Slark." in "\n".join(lines)  # the advice is still readable
    assert not any("\x1b" in line or "\x07" in line for line in lines)


def test_console_text_strips_terminal_controls():
    cleaned = display_text("Buy Slark. \x1b[2J\x07\u202e")
    assert "Buy Slark." in cleaned
    # Without its ESC byte the rest of the sequence is inert text.
    assert not any(char in cleaned for char in ("\x1b", "\x07", "\u202e"))
    assert display_text(12) == "12"


def test_ask_reply_is_printed_as_text(monkeypatch, capsys):
    from gamebuddy import cli

    monkeypatch.setattr(cli, "is_running", lambda: True)
    monkeypatch.setattr(
        cli, "send_command", lambda *a, **k: {"ok": True, "reply": "Buy Slark. \x1b[2J\x1b[H"}
    )
    assert cli.main(["ask", "what now"]) == 0
    out = capsys.readouterr().out
    assert "Buy Slark." in out
    assert "\x1b" not in out


def test_ask_error_is_printed_as_text(monkeypatch, capsys):
    from gamebuddy import cli

    monkeypatch.setattr(cli, "is_running", lambda: True)
    monkeypatch.setattr(cli, "send_command", lambda *a, **k: {"ok": False, "error": "\x1b]0;owned\x07"})
    assert cli.main(["ask", "what now"]) == 1
    err = capsys.readouterr().err
    assert "\x1b" not in err and "\x07" not in err
