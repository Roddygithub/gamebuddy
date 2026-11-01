"""CodexProvider against a fake `codex` executable on PATH."""

import json
import os
import stat
from pathlib import Path

import pytest

from gamebuddy.llm.base import Message, image_part
from gamebuddy.llm.codex_provider import CodexError, CodexProvider, parse_envelope
from gamebuddy.tools import ToolContext, build_tools

FAKE = r"""#!/usr/bin/env bash
# Records argv + stdin, writes a canned envelope to the -o file.
log="$FAKE_CODEX_LOG"
printf '%s\n' "$@" > "$log.args"
cat > "$log.prompt"
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift ;;
  esac
  shift
done
if [ -n "$FAKE_CODEX_FAIL" ]; then echo "$FAKE_CODEX_FAIL" >&2; exit 1; fi
printf '%s' "$FAKE_CODEX_REPLY" > "$out"
"""


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "codex"
    exe.write_text(FAKE)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    log = tmp_path / "log"
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    monkeypatch.delenv("FAKE_CODEX_FAIL", raising=False)
    return log


def _tools():
    ctx = ToolContext(
        pin=lambda *a: None,
        unpin=lambda: None,
        remember=lambda *a: None,
        recall=lambda q: [],
        web_enabled=False,
    )
    return build_tools(ctx)


def test_envelope_roundtrip_with_image(fake_codex, monkeypatch):
    env = {
        "reply": "",
        "actions": [{"name": "pin_content", "arguments": json.dumps({"title": "T", "markdown": "- x"})}],
    }
    monkeypatch.setenv("FAKE_CODEX_REPLY", json.dumps(env))
    p = CodexProvider(model="gpt-5", effort="low")
    msgs = [Message(role="user", content="pin this", images=[image_part(b"\xff\xd8", "image/jpeg")])]
    deltas = []
    turn = p.chat("SYS", msgs, tools=_tools(), on_text=deltas.append)
    assert turn.text == "" and deltas == []
    assert [c.name for c in turn.tool_calls] == ["pin_content"]
    assert turn.tool_calls[0].arguments["title"] == "T"
    args = Path(f"{fake_codex}.args").read_text().strip().split("\n")
    assert args[:2] == ["exec", "--skip-git-repo-check"]
    assert "--ephemeral" in args and "--output-schema" in args and "-i" in args
    assert args[args.index("-m") + 1] == "gpt-5"
    assert 'model_reasoning_effort="low"' in args
    assert args[-1] == "-"
    img = Path(args[args.index("-i") + 1])
    assert img.suffix == ".jpg"
    prompt = Path(f"{fake_codex}.prompt").read_text()
    assert "<instructions>\nSYS\n</instructions>" in prompt
    assert "- pin_content(" in prompt and "[user, screenshot attached]" in prompt


def test_tool_results_rendered_and_plain_reply(fake_codex, monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_REPLY", json.dumps({"reply": "Pinned.", "actions": []}))
    p = CodexProvider()
    from gamebuddy.llm.base import ToolCall

    msgs = [
        Message(role="user", content="pin"),
        Message(role="assistant", tool_calls=[ToolCall("a0", "pin_content", {"title": "T"})]),
        Message(role="tool", content="Pinned 'T'.", tool_call_id="a0"),
    ]
    turn = p.chat("SYS", msgs, tools=_tools())
    assert turn.text == "Pinned." and turn.tool_calls == []
    prompt = Path(f"{fake_codex}.prompt").read_text()
    assert "[assistant action] pin_content(" in prompt and "[action result]\nPinned 'T'." in prompt
    args = Path(f"{fake_codex}.args").read_text().strip().split("\n")
    assert "-m" not in args  # default model


def test_json_mode_returns_raw_text(fake_codex, monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_REPLY", '{"decision": "ABSTAIN"}')
    turn = CodexProvider().chat("SYS", [Message(role="user", content="observe")], json_mode=True)
    assert turn.text == '{"decision": "ABSTAIN"}'
    assert "--output-schema" not in Path(f"{fake_codex}.args").read_text()


def test_errors(fake_codex, monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_FAIL", "error: not logged in, run codex login")
    with pytest.raises(CodexError, match="codex_not_logged_in"):
        CodexProvider().chat("S", [Message(role="user", content="x")])
    monkeypatch.setenv("FAKE_CODEX_FAIL", "boom")
    with pytest.raises(CodexError, match="codex_failed"):
        CodexProvider().chat("S", [Message(role="user", content="x")])
    with pytest.raises(CodexError, match="codex_not_installed"):
        CodexProvider(binary="definitely-not-codex-xyz").chat("S", [Message(role="user", content="x")])


def test_parse_envelope_tolerant():
    reply, calls = parse_envelope(
        'Sure:\n```json\n{"reply": "hi", "actions": [{"name": "recall", "arguments": "{\\"query\\": \\"slark\\"}"}]}\n```'
    )
    assert reply == "hi" and calls[0].arguments == {"query": "slark"}
    assert parse_envelope("plain text answer") == ("plain text answer", [])
    reply, calls = parse_envelope(
        '{"reply": "x", "actions": [{"name": "remember", "arguments": {"note": "n"}}]}'
    )
    assert calls[0].arguments == {"note": "n"}


def test_router_builds_codex_and_ignores_claude_default():
    from gamebuddy.config import Config
    from gamebuddy.llm.router import make_provider

    cfg = Config()
    cfg.llm.provider = "codex"
    p = make_provider(cfg)
    assert p.name == "codex" and p.model == ""  # claude-opus-5-5 default ignored
    cfg.llm.model = "gpt-5"
    assert make_provider(cfg).model == "gpt-5"


def test_codex_disables_desktop_connectors_for_buddy(fake_codex, monkeypatch, tmp_path):
    home = tmp_path / "codex-home"
    home.mkdir()
    config = '[mcp_servers.prev]\ncommand="/usr/bin/prev"\nargs=["--mcp"]\n[plugins."desktop@local"]\nenabled=true\n'
    (home / "config.toml").write_text(config)
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("FAKE_CODEX_REPLY", "Ready")
    CodexProvider().chat("S", [Message(role="user", content="hello")])
    args = Path(f"{fake_codex}.args").read_text().splitlines()
    assert "mcp_servers.prev.enabled=false" in args
    assert "plugins.desktop@local.enabled=false" in args
    assert "features.shell_tool=false" in args
    assert (home / "config.toml").read_text() == config


def test_codex_fails_before_launch_if_connector_cannot_be_disabled(fake_codex, monkeypatch, tmp_path):
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "config.toml").write_text('[mcp_servers."desktop.prev"]\ncommand="prev"\n')
    monkeypatch.setenv("CODEX_HOME", str(home))
    with pytest.raises(CodexError, match="codex_mcp_name_unsupported"):
        CodexProvider().chat("S", [Message(role="user", content="hello")])
    assert not Path(f"{fake_codex}.args").exists()
