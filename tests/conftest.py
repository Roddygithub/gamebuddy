import os
import pathlib
import tempfile

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never touch the real ~/.config or ~/.local while testing."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    pathlib.Path(tmp_path / "run").mkdir()
    short = pathlib.Path(tempfile.mkdtemp(prefix="gb", dir="/tmp"))
    monkeypatch.setenv("GAMEBUDDY_SOCKET", str(short / "gb.sock"))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    yield
    os.environ.pop("GAMEBUDDY_SOCKET", None)


class FakeProvider:
    """Scripted provider: a list of ChatTurn-like dicts consumed in order."""

    name = "fake"
    model = "fake-1"

    def __init__(self, script):
        from gamebuddy.llm.base import ChatTurn, ToolCall

        self.turns = []
        for item in script:
            calls = [ToolCall(id=c[0], name=c[1], arguments=c[2]) for c in item.get("calls", [])]
            self.turns.append(ChatTurn(text=item.get("text", ""), tool_calls=calls))
        self.requests = []

    def supports_vision(self):
        return True

    def chat(self, system, messages, tools=None, on_text=None, max_tokens=None, json_mode=False):
        self.requests.append(
            {"system": system, "messages": list(messages), "tools": tools, "json": json_mode}
        )
        turn = self.turns.pop(0)
        if on_text and turn.text:
            on_text(turn.text)
        return turn


@pytest.fixture
def fake_provider():
    return FakeProvider
