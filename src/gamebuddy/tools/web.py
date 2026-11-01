"""Web search and safe public-page fetch — the only network tools Buddy has."""

from __future__ import annotations

import html
import http.client
import ipaddress
import re
import socket
import ssl
from urllib.parse import quote, urljoin, urlsplit

import httpx

_TAG_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v\xa0]+")
_NL_RE = re.compile(r"\n\s*\n+")
_REDIRECTS = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 5
_MAX_BODY_BYTES = 1_000_000
_USER_AGENT = "GameBuddy/0.1 (+https://github.com/Roddygithub/gamebuddy)"
_NAT64_WELL_KNOWN = ipaddress.IPv6Network("64:ff9b::/96")


class _UnsafeTarget(ValueError):
    pass


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


def _parse_target(url: str) -> tuple[str, str, int, str, str]:
    if any(ord(char) < 32 or ord(char) == 127 for char in url):
        raise _UnsafeTarget("control characters are not allowed in URLs")
    try:
        parts = urlsplit(url)
        raw_host = parts.hostname
        explicit_port = parts.port
    except ValueError as exc:
        raise _UnsafeTarget("invalid URL") from exc

    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise _UnsafeTarget("only http(s) URLs are allowed")
    if not raw_host or parts.username is not None or parts.password is not None:
        raise _UnsafeTarget("URL must have a hostname and no embedded credentials")
    if "%" in raw_host:
        # Reject scoped IPv6 literals and percent-encoded host tricks.
        raise _UnsafeTarget("scoped or escaped hostnames are not allowed")

    default_port = 80 if scheme == "http" else 443
    if explicit_port not in {None, default_port}:
        raise _UnsafeTarget("only standard HTTP/HTTPS ports are allowed")
    port = default_port

    try:
        host = raw_host if ":" in raw_host else raw_host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise _UnsafeTarget("invalid hostname") from exc

    host_header = f"[{host}]" if ":" in host else host
    path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
    if parts.query:
        path += "?" + quote(parts.query, safe="/?%:@!$&'()*+,;=-._~")
    return scheme, host, port, path, host_header


def _public_addresses(host: str, port: int) -> list[str]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise OSError(f"could not resolve {host}") from exc
        addresses = list(dict.fromkeys(record[4][0] for record in records))
    else:
        addresses = [str(literal)]

    if not addresses:
        raise OSError(f"no addresses found for {host}")
    parsed = [ipaddress.ip_address(address) for address in addresses]
    if any(not _is_public_address(address) for address in parsed):
        raise _UnsafeTarget("hostname resolves to a non-public address")
    return addresses


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if not address.is_global:
        return False
    if not isinstance(address, ipaddress.IPv6Address):
        return True
    # Do not let transition/tunnel addresses hide a private IPv4 destination.
    if address.sixtofour is not None or address.teredo is not None:
        return False
    if address in _NAT64_WELL_KNOWN:
        embedded_ipv4 = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
        return embedded_ipv4.is_global
    return True


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float):
        super().__init__(host=host, port=port, timeout=timeout)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float):
        super().__init__(host=host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def _request_public(
    *, scheme: str, host: str, port: int, host_header: str, target: str, address: str, timeout: float
) -> tuple[int, dict[str, str], bytes]:
    connection_type = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    connection = connection_type(host, port, address, timeout)
    try:
        connection.request(
            "GET",
            target,
            headers={
                "Host": host_header,
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.1",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        headers = {name.lower(): value for name, value in response.getheaders()}
        body = b"" if response.status in _REDIRECTS else response.read(_MAX_BODY_BYTES + 1)
        return response.status, headers, body
    finally:
        connection.close()


def _fetch_response(
    scheme: str, host: str, port: int, path: str, host_header: str, timeout: float
) -> tuple[int, dict[str, str], bytes]:
    addresses = _public_addresses(host, port)
    last_error: OSError | http.client.HTTPException | None = None
    for address in addresses:
        try:
            return _request_public(
                scheme=scheme,
                host=host,
                port=port,
                host_header=host_header,
                target=path,
                address=address,
                timeout=timeout,
            )
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise OSError("no public addresses are available")


def fetch_page(url: str, max_chars: int = 6000, timeout: float = 12.0) -> str:
    """Fetch a public HTTP(S) page, pinning each request to a public IP.

    Redirects are followed manually so every new destination is parsed,
    resolved, checked, and pinned separately. This prevents model-controlled
    URLs and redirects from reaching loopback or private-network services.
    """

    current_url = url
    for redirect_count in range(_MAX_REDIRECTS + 1):
        try:
            scheme, host, port, path, host_header = _parse_target(current_url)
            status, headers, raw = _fetch_response(scheme, host, port, path, host_header, timeout)
        except _UnsafeTarget as exc:
            return f"Refused: {exc}."
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            return f"Fetch failed: {exc}"

        if status in _REDIRECTS:
            location = headers.get("location", "").strip()
            if not location:
                return "Fetch failed: redirect had no destination."
            if redirect_count == _MAX_REDIRECTS:
                return "Refused: too many redirects."
            current_url = urljoin(current_url, location)
            continue
        if not 200 <= status < 300:
            return f"Fetch failed: HTTP {status}."

        content_type = headers.get("content-type", "")
        if not any(kind in content_type.lower() for kind in ("html", "text", "json")):
            return f"Unsupported content type: {content_type}"
        content_encoding = headers.get("content-encoding", "identity").lower()
        if content_encoding not in {"", "identity"}:
            return f"Unsupported content encoding: {content_encoding}"

        body_truncated = len(raw) > _MAX_BODY_BYTES
        response = httpx.Response(
            status, headers={"content-type": content_type}, content=raw[:_MAX_BODY_BYTES]
        )
        body = response.text
        text = html_to_text(body) if "html" in content_type.lower() else body
        if len(text) > max_chars:
            text = text[:max_chars] + "\n…(truncated)"
        elif body_truncated:
            text += "\n…(truncated)"
        return text or f"Unsupported content type: {content_type}"

    return "Refused: too many redirects."
