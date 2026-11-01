import json

from gamebuddy.llm.catalog import codex_models, reasoning_levels
from gamebuddy.llm.codex_provider import CodexProvider


def test_catalog_filters_hidden_models_and_uses_model_efforts(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "models_cache.json").write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "test-model",
                        "visibility": "list",
                        "supported_reasoning_levels": [{"effort": "low"}, {"effort": "max"}],
                    },
                    {"slug": "hidden", "visibility": "hide"},
                    None,
                ]
            }
        )
    )
    assert [m["slug"] for m in codex_models()] == ["test-model"]
    assert reasoning_levels("codex", "test-model") == ["low", "max"]
    assert CodexProvider(effort="max").effort == "max"
    assert reasoning_levels("ollama", "test-model") == []


def test_missing_or_invalid_catalog_is_optional(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert codex_models() == []
    (tmp_path / "models_cache.json").write_text("[]")
    assert codex_models() == []
    assert reasoning_levels("codex", "custom") == ["low", "medium", "high", "xhigh"]
