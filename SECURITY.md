# Security

- GameBro runs as your user, with no privileges and no network service: the only socket is a
  mode-600 Unix socket in `$XDG_RUNTIME_DIR`.
- Network traffic goes to the AI provider you configured, to DuckDuckGo for `web_search`, and
  to pages the model asks to read with `fetch_page` (http/https only, 6 000 characters max).
- API keys are read from the environment or from `~/.config/gamebro/config.toml` (chmod 600).
- Screenshots are kept in memory only.

Report vulnerabilities through GitHub private vulnerability reporting or an issue without
exploit details.
