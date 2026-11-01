from gamebro.config import Config
from gamebro.kin import Kin, KinCallbacks
from gamebro.llm.base import Message, ToolCall
from gamebro.memory import Store


def test_store_roundtrip(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    s.add_message(Message(role="user", content="hi"))
    s.add_message(Message(role="assistant", content="hello", tool_calls=[ToolCall("1", "pin_content", {})]))
    # trailing tool call without result must be dropped from the replayable history
    assert [m.role for m in s.recent_messages()] == ["user"]
    s.add_message(Message(role="tool", content="done", tool_call_id="1"))
    s.add_message(Message(role="assistant", content="pinned"))
    assert [m.role for m in s.recent_messages()] == ["user", "assistant", "tool", "assistant"]
    s.remember("plays Slark", game="Underlords")
    assert s.memories(game="Underlords") == ["plays Slark"]
    assert s.search_memories("slark") == ["plays Slark"]
    s.save_pin("Build", "- a\n- b", "build")
    assert s.load_pin()["kind"] == "build"
    s.clear_pin()
    assert s.load_pin() is None
    s.log_coach("gate", "accepted", "x")
    assert s.coach_stats()["gate:accepted"] == 1
    s.close()


def test_kin_tool_loop_pins_and_remembers(tmp_path, fake_provider):
    cfg = Config()
    cfg.llm.web_search = False
    store = Store(tmp_path / "db.sqlite")
    events = {"pins": [], "text": [], "done": [], "status": []}
    cb = KinCallbacks(
        on_pin=lambda t, md, k: events["pins"].append((t, md, k)),
        on_text_delta=events["text"].append,
        on_reply_done=events["done"].append,
        on_status=events["status"].append,
    )
    provider = fake_provider(
        [
            {
                "text": "",
                "calls": [
                    (
                        "c1",
                        "pin_content",
                        {"title": "Samurai build", "markdown": "- Uchigatana", "kind": "build"},
                    ),
                    ("c2", "remember", {"note": "Prefers dex builds"}),
                ],
            },
            {"text": "Pinned your build."},
        ]
    )
    kin = Kin(cfg, store, cb, provider=provider)
    kin.game_title = "Elden Ring"
    reply = kin.ask("pin my build", screenshot=b"\xff\xd8fake")
    assert reply == "Pinned your build."
    assert events["pins"] == [("Samurai build", "- Uchigatana", "build")]
    assert store.memories() == ["Prefers dex builds"]
    assert store.load_pin()["title"] == "Samurai build"
    # second request carried the tool results back to the model
    second = provider.requests[1]["messages"]
    assert [m.role for m in second][-3:] == ["assistant", "tool", "tool"]
    assert "Elden Ring" in provider.requests[0]["system"]
    assert provider.requests[0]["messages"][-1].images  # screenshot attached
    assert events["done"] == ["Pinned your build."]
    assert events["status"][-1] == "ready"
    store.close()


def test_kin_reports_errors(tmp_path):
    class Boom:
        name = "boom"

        def supports_vision(self):
            return False

        def chat(self, **kw):
            raise RuntimeError("api down")

    errors = []
    kin = Kin(Config(), Store(tmp_path / "db.sqlite"), KinCallbacks(on_error=errors.append), provider=Boom())
    assert kin.ask("hello") == ""
    assert errors == ["api down"]
