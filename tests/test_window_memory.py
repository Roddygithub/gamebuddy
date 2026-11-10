"""The chosen game window survives a restart, without guessing between candidates."""

from gamebuddy.capture import Rect, WindowInfo
from gamebuddy.capture.base import find_same_window, load_remembered_window, remember_window


def win(window_id: str, title: str, app_id: str) -> WindowInfo:
    return WindowInfo(id=window_id, title=title, app_id=app_id, rect=Rect(0, 0, 1920, 1080))


def test_exact_title_match_wins_over_another_window_of_the_same_app():
    windows = [
        win("1", "Dota 2 — Boutique", "steam_app_570"),
        win("2", "Dota 2", "steam_app_570"),
    ]
    assert find_same_window(windows, "steam_app_570", "Dota 2").id == "2"


def test_single_window_of_the_app_survives_a_title_change():
    windows = [win("7", "Dota 2 — Menu principal", "steam_app_570")]
    assert find_same_window(windows, "steam_app_570", "Dota 2").id == "7"


def test_ambiguous_match_is_not_guessed():
    windows = [
        win("1", "Dota 2 — Boutique", "steam_app_570"),
        win("2", "Dota 2 — Draft", "steam_app_570"),
    ]
    assert find_same_window(windows, "steam_app_570", "Dota 2") is None


def test_other_applications_are_never_matched():
    windows = [win("1", "Patch notes", "vivaldi-stable"), win("2", "Terminal", "Alacritty")]
    assert find_same_window(windows, "steam_app_570", "Dota 2") is None


def test_own_widget_is_never_matched():
    windows = [win("1", "GameBuddy", "gamebuddy")]
    assert find_same_window(windows, "gamebuddy", "GameBuddy") is None


def test_remember_round_trip_and_forgetting(tmp_path):
    path = tmp_path / "window.json"
    assert load_remembered_window(path) == ("", "")
    remember_window(win("1", "Dota 2", "steam_app_570"), path)
    assert load_remembered_window(path) == ("steam_app_570", "Dota 2")
    remember_window(None, path)
    assert not path.exists()
    assert load_remembered_window(path) == ("", "")


def test_unreadable_state_is_ignored(tmp_path):
    path = tmp_path / "window.json"
    path.write_text("{not json")
    assert load_remembered_window(path) == ("", "")
    path.write_text('["steam_app_570"]')
    assert load_remembered_window(path) == ("", "")
