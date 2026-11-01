"""Web search and page fetch — the only network tools Buddy has."""

from __future__ import annotations

import html
import re

import httpx

_TAG_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v\xa0]+")
_NL_RE = re.compile(r"\n\s*\n+")


def web_search(query: str, max_results: int = 5, region: str = "wt-wt") -> list[dict[str, str]]:
    from ddgs import DDGS

    results: list[dict[str, str]] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, region=region, max_results=max_results) or []:
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("href", "") or item.get("url", ""),
                    "snippet": item.get("body", ""),
                }
            )
    return results


def format_results(results: list[dict[str, str]]) -> str:
    if not results:
        return "No results."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
    return "\n".join(lines)


def html_to_text(raw: str) -> str:
    raw = _TAG_RE.sub(" ", raw)
    raw = re.sub(r"<br\s*/?>|</p>|</div>|</h\d>|</li>|</tr>", "\n", raw, flags=re.I)
    text = _HTML_RE.sub(" ", raw)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def fetch_page(url: str, max_chars: int = 6000, timeout: float = 12.0) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return "Refused: only http(s) URLs."
    headers = {"User-Agent": "GameBuddy/0.1 (+https://github.com/Roddygithub/gamebuddy)"}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        body = resp.text if "html" in ctype or "text" in ctype or "json" in ctype else ""
    if not body:
        return f"Unsupported content type: {ctype}"
    text = html_to_text(body) if "html" in ctype else body
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…(truncated)"
    return text
