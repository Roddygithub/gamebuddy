# IPC protocol

Socket: `$XDG_RUNTIME_DIR/gamebuddy.sock` (override with `GAMEBUDDY_SOCKET`). Newline-delimited JSON.
One request per line; one response per line.

| Request | Response |
|---|---|
| `{"cmd":"ping"}` | `{"ok":true,"app":"gamebuddy"}` |
| `{"cmd":"status"}` | `{"ok":true,"visible":…,"window":…,"recording":…,"hands_free":…,"coach":…,"busy":…,"backend":…,"language":…}` |
| `{"cmd":"windows"}` | `{"ok":true,"windows":[{"id":…,"title":…,"app_id":…,"rect":{x,y,w,h}}]}` |
| `{"cmd":"ptt","action":"start|stop|toggle"}` | `{"ok":true,"queued":"ptt"}` |
| `{"cmd":"ask","text":"…"}` | `{"ok":true,"queued":"ask"}` (fire and forget) |
| `{"cmd":"ask","text":"…","wait":true}` | `{"ok":true,"reply":"…"}` or `{"ok":false,"error":"…"}` once answered |
| `{"cmd":"toggle"}` / `show` / `hide` / `unpin` / `settings` / `quit` | queued |
| `{"cmd":"listen","action":"on|off|toggle"}` | queued |
| `{"cmd":"coach","action":"on|off|toggle"}` | queued |
| `{"cmd":"select_window","id":"…"}` / `{"cmd":"pick_window"}` | queued |
| `{"cmd":"subscribe"}` | `{"ok":true,"subscribed":true}` then a stream of events |

Events: `{"event":"status","key":"listening"}`, `{"event":"window","title":…,"id":…}`,
`{"event":"coach","advice":…}`.

Example from a shell:

```bash
printf '{"cmd":"ask","text":"which of these three items?","wait":true}\n' | socat - UNIX-CONNECT:"$XDG_RUNTIME_DIR/gamebuddy.sock"
```

`gamebuddy ask "…"` uses the waiting form and prints the answer; `--no-wait` keeps the queued form.
