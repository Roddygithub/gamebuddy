"""GameBuddy speaks every language `omarchy language list` offers."""

from __future__ import annotations

import re

import pytest

from gamebuddy import i18n

# `jq 'keys' /usr/share/omarchy/default/i18n/locales.json`
OMARCHY_CODES = (
    "ar bg bn ca cs da de el en es-MX et fa fi fil fr ga he hi hr hu id is it ja "
    "ko lt lv ms nl no pl pt pt-BR ro ru si sk sl sr sv sw ta th tr uk ur uz vi zh-CN zh-TW"
).split()


def test_every_omarchy_language_has_a_table():
    assert len(OMARCHY_CODES) == 50
    for code in OMARCHY_CODES:
        assert i18n._resolve(code) in i18n._STRINGS, code
    assert len(i18n.SUPPORTED_LANGUAGES) == 50


def test_tables_share_the_english_keys_and_placeholders():
    reference = i18n._STRINGS["en"]
    for code, table in i18n._STRINGS.items():
        assert set(table) == set(reference), code
        for key, text in reference.items():
            expected = sorted(re.findall(r"\{(\w+)\}", text))
            assert sorted(re.findall(r"\{(\w+)\}", table[key])) == expected, (code, key)


@pytest.mark.parametrize("code", ["ar", "he", "fa", "ur"])
def test_rtl_languages_are_flagged(code):
    assert i18n.is_rtl(code)


def test_omarchy_choice_wins_over_the_session_locale(tmp_path, monkeypatch):
    language_file = tmp_path / "language"
    language_file.write_text("da\n")
    monkeypatch.setattr(i18n, "OMARCHY_LANGUAGE_FILE", language_file)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n.detect_language() == "da"


def test_omarchy_aliases_and_unset_file(tmp_path, monkeypatch):
    language_file = tmp_path / "missing"
    monkeypatch.setattr(i18n, "OMARCHY_LANGUAGE_FILE", language_file)
    monkeypatch.setenv("LANG", "es_MX.UTF-8")
    assert i18n.detect_language() == "es"
    monkeypatch.setenv("LANG", "pt_PT.UTF-8")
    assert i18n.detect_language() == "pt-PT"
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    assert i18n.detect_language() == "zh-CN"
