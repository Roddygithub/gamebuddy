"""The eval summary prints foreign text as text, never as terminal commands."""

from __future__ import annotations

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
