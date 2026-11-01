# Omarchy plugin and marketplace submission

GameBuddy's repository root is an Omarchy Quattro `bar-widget` plugin:
`io.github.roddygithub.gamebuddy`. The same repository ships the separately
installed Python engine. Installing/enabling the bar plugin never runs
`install.sh`, requests privilege or downloads voice models automatically.

## Runtime

- Left click: start the engine, or show/hide the overlay when it is running.
- Right click: open AI settings on a running engine.
- Middle click: choose the game window on a running engine.
- The head is loaded from the repository's own symbolic SVG and recolored by
  the bar foreground; listening uses the host's active color.
- `shell summon` and `shell hide` forward to the external engine.
- A five-second timer queries status; checks never overlap. The timer and its
  short-lived processes belong to the widget and stop when it is unloaded.
- Starting the engine uses a detached process, so disabling/removing the widget
  does not unexpectedly terminate a conversation. The engine can also run through
  its independently installed user service.
- No second Quickshell instance, additional shell singleton or global theme
  changes are needed. Credentials belong to the engine configuration/environment,
  never to `shell.json` or the QML widget.

See the root README for dependencies, all installer effects, update policy,
privacy boundaries and both partial/full removal instructions.

## Validation

```sh
omarchy plugin validate /path/to/gamebuddy
# qmllint needs the virtual qs namespace mapped to the installed shell.
mkdir -p /tmp/gamebuddy-qml-imports
ln -sfn /usr/share/omarchy/shell /tmp/gamebuddy-qml-imports/qs
/usr/lib/qt6/bin/qmllint -I /tmp/gamebuddy-qml-imports BarWidget.qml
bash -n install.sh plugin-control.sh
pytest -q
```

The import mapping is a lint-only directory outside the plugin. The distributed
plugin contains no symlinks. Live tests on Omarchy Quattro covered discovery,
enabling, engine startup, show/hide routes, disabling and re-enabling, with the
symbolic head visible in the bar. Shell-global reloads can briefly delay the CLI
response; inspect `omarchy plugin list --json` before retrying an operation.
A temporary plugin copy was used, and the user's original bar layout restored.

`preview.png` contains only this project's own UI, icon and demo text. Regenerate
it with `python docs/make-plugin-preview.py` in an environment containing GameBuddy
and PySide6. No game artwork, private chat, microphone or AI request is used.

## Proposed listing

- Title: `[Plugin]: GameBuddy`
- Repository: https://github.com/Roddygithub/gamebuddy
- Category: `Productivity`
- Tags: `ai, games, bar`
- Body: [marketplace-submission.md](marketplace-submission.md)

The current registry was checked for the exact plugin ID before preparation;
it was not present. A listing is not created simply by merging this code.
The owner's approval of the completed submission and all five checklist items
is required before opening a marketplace issue. After submission, publication
requires the marketplace's exact-commit automated validation and a maintainer's
approval. No approval, verification badge or publication is claimed here.

References:

- [Marketplace publishing guide](https://plugins.omarchy.org/publish.html)
- [CLI/AI submission instructions](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md)
- [Omarchy development guide](https://plugins.omarchy.org/develop.html)
