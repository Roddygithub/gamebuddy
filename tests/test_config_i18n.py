from gamebuddy import i18n
from gamebuddy.config import Config, load_config, save_config
from gamebuddy.i18n import Translator, detect_language


def test_roundtrip(tmp_path):
    cfg = Config()
    cfg.llm.provider = "ollama"
    cfg.llm.model = "llama3.2-vision"
    cfg.coach.enabled = True
    path = save_config(cfg, tmp_path / "c.toml")
    assert oct(path.stat().st_mode)[-3:] == "600"
    loaded = load_config(path)
    assert loaded.llm.provider == "ollama"
    assert loaded.coach.enabled is True
    assert loaded.ui.width == 420  # default kept


def test_unknown_keys_ignored(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[llm]\nprovider = "openai"\nfuture_option = 1\n[nope]\nx = 2\n')
    cfg = load_config(p)
    assert cfg.llm.provider == "openai"


def test_api_key_resolution(monkeypatch):
    cfg = Config()
    assert cfg.resolve_api_key() == ""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert cfg.resolve_api_key() == "sk-test"
    cfg.llm.api_key = "inline"
    assert cfg.resolve_api_key() == "inline"


def test_translator_fallback_and_format():
    tr = Translator("fr")
    assert tr("ready") == "Prêt quand tu veux"
    assert "Alt+V" in tr("hold_hint", key="Alt+V")
    tr.set_language("xx")
    assert tr.language == "en"
    assert tr("missing_key") == "missing_key"


def test_detect_language(monkeypatch, tmp_path):
    # Omarchy's own choice outranks LANG; keep it out of this test.
    monkeypatch.setattr(i18n, "OMARCHY_LANGUAGE_FILE", tmp_path / "language")
    monkeypatch.setenv("LC_ALL", "pt_BR.UTF-8")
    assert detect_language() == "pt-BR"
    monkeypatch.setenv("LC_ALL", "pt_PT.UTF-8")
    assert detect_language() == "pt-PT"
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    assert detect_language() == "de"
    monkeypatch.setenv("LC_ALL", "ja_JP.UTF-8")
    assert detect_language() == "ja"
    monkeypatch.setenv("LC_ALL", "xx_YY.UTF-8")
    assert detect_language() == "en"


def test_all_languages_have_all_keys():
    from gamebuddy.i18n import _STRINGS

    base = set(_STRINGS["en"])
    for lang, table in _STRINGS.items():
        assert base <= set(table), lang


def test_failed_save_preserves_config_and_removes_temporary(tmp_path, monkeypatch):
    import pytest

    from gamebuddy import config

    path = save_config(Config(), tmp_path / "config.toml")
    original = path.read_bytes()

    def fail_dump(data, fh):
        import os

        assert os.fstat(fh.fileno()).st_mode & 0o777 == 0o600
        fh.write(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(config.tomli_w, "dump", fail_dump)
    with pytest.raises(OSError, match="disk full"):
        save_config(Config(), path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".config.toml.*"))
