from gamebuddy.llm.anthropic_provider import AnthropicProvider
from gamebuddy.llm.base import Message, ToolCall, image_part
from gamebuddy.llm.openai_provider import OpenAIProvider


def _history():
    return [
        Message(role="user", content="what is this?", images=[image_part(b"abc", "image/jpeg")]),
        Message(role="assistant", content="", tool_calls=[ToolCall("t1", "web_search", {"query": "x"})]),
        Message(role="tool", content="results", tool_call_id="t1"),
        Message(role="tool", content="more", tool_call_id="t2"),
        Message(role="assistant", content="Here you go."),
        Message(role="user", content="thanks"),
    ]


def test_anthropic_conversion_groups_tool_results_and_alternates():
    api = AnthropicProvider._to_api(_history())
    roles = [m["role"] for m in api]
    assert roles == ["user", "assistant", "user", "assistant", "user"]
    assert api[0]["content"][0]["type"] == "image"
    assert api[1]["content"][0]["type"] == "tool_use"
    assert [b["tool_use_id"] for b in api[2]["content"]] == ["t1", "t2"]


def test_anthropic_replays_raw_assistant_blocks():
    raw = [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "text", "text": "ok"}]
    api = AnthropicProvider._to_api(
        [Message(role="user", content="q"), Message(role="assistant", raw=raw, provider="anthropic")]
    )
    assert api[1]["content"] == raw


def test_openai_conversion():
    api = OpenAIProvider._to_api("sys", _history())
    assert api[0] == {"role": "system", "content": "sys"}
    assert api[1]["content"][0]["type"] == "image_url"
    assert api[2]["tool_calls"][0]["function"]["name"] == "web_search"
    assert api[3] == {"role": "tool", "tool_call_id": "t1", "content": "results"}


def test_tool_schema_shapes():
    from gamebuddy.tools import ToolContext, build_tools

    ctx = ToolContext(pin=lambda *a: None, unpin=lambda: None, remember=lambda *a: None, recall=lambda q: [])
    tools = build_tools(ctx)
    names = {t.name for t in tools}
    assert {"pin_content", "unpin_content", "remember", "recall", "web_search", "fetch_page"} == names
    assert all(t.parameters["type"] == "object" for t in tools)
    a = AnthropicProvider._tools(tools)
    o = OpenAIProvider._tools(tools)
    assert a[0]["input_schema"] == o[0]["function"]["parameters"]
