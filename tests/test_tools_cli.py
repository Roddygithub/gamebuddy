from gamebuddy.cli import hyprland_config, main
from gamebuddy.tools.web import html_to_text


def test_html_to_text():
    html = "<html><head><style>x{}</style><script>bad()</script></head><body><h1>Title</h1><p>Hello&nbsp;<b>world</b></p></body></html>"
    text = html_to_text(html)
    assert "bad()" not in text and "Title" in text and "Hello world" in text


def test_hyprland_config_variants():
    legacy = hyprland_config("legacy")
    assert "windowrulev2 = pin, class:^(gamebuddy)$" in legacy
    assert "bind = ALT, V, exec, gamebuddy ptt start" in legacy
    assert "bindr = ALT, V, exec, gamebuddy ptt stop" in legacy
    new = hyprland_config("v053")
    assert "match:class ^(gamebuddy)$, pin on" in new
    lua = hyprland_config("lua")
    assert "hl.window_rule" in lua


def test_cli_without_widget_running(capsys):
    assert main(["ptt", "start"]) == 3
    assert main(["config", "path"]) == 0
    assert "config.toml" in capsys.readouterr().out
    assert main(["hyprland-config", "--syntax", "legacy"]) == 0
