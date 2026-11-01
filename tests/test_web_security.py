import socket

import pytest

from gamebuddy.tools import web


def _dns_record(address: str, port: int):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
    return family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr


@pytest.mark.parametrize("url", ["http://127.0.0.1/admin", "http://[::1]/admin"])
def test_refuses_literal_loopback_addresses(url, monkeypatch):
    requests = []
    monkeypatch.setattr(web, "_request_public", lambda **kwargs: requests.append(kwargs))

    result = web.fetch_page(url)

    assert result.startswith("Refused:")
    assert requests == []


def test_refuses_nat64_address_with_embedded_loopback():
    result = web.fetch_page("http://[64:ff9b::7f00:1]/admin")

    assert result.startswith("Refused:")


def test_refuses_hostname_resolving_to_private_address(monkeypatch):
    monkeypatch.setattr(
        web.socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [_dns_record("10.0.0.8", port)],
    )
    requests = []
    monkeypatch.setattr(web, "_request_public", lambda **kwargs: requests.append(kwargs))

    result = web.fetch_page("https://private.example/account")

    assert result.startswith("Refused:")
    assert requests == []


def test_refuses_mixed_public_and_private_dns_answers(monkeypatch):
    monkeypatch.setattr(
        web.socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [
            _dns_record("93.184.216.34", port),
            _dns_record("10.0.0.8", port),
        ],
    )
    requests = []
    monkeypatch.setattr(web, "_request_public", lambda **kwargs: requests.append(kwargs))

    result = web.fetch_page("https://mixed.example/")

    assert result.startswith("Refused:")
    assert requests == []


def test_public_hostname_is_requested_through_its_checked_ip(monkeypatch):
    monkeypatch.setattr(
        web.socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [_dns_record("93.184.216.34", port)],
    )
    requests = []

    def request(**kwargs):
        requests.append(kwargs)
        return 200, {"content-type": "text/plain; charset=utf-8"}, b"Public guide"

    monkeypatch.setattr(web, "_request_public", request)

    assert web.fetch_page("https://guide.example/build") == "Public guide"
    assert requests[0]["address"] == "93.184.216.34"
    assert requests[0]["host"] == "guide.example"
    assert requests[0]["target"] == "/build"


def test_public_to_private_redirect_is_refused(monkeypatch):
    def resolve(host, port, **kwargs):
        address = "93.184.216.34" if host == "public.example" else "192.168.1.10"
        return [_dns_record(address, port)]

    monkeypatch.setattr(web.socket, "getaddrinfo", resolve)
    requests = []

    def request(**kwargs):
        requests.append(kwargs)
        return 302, {"location": "http://private.example/secrets"}, b""

    monkeypatch.setattr(web, "_request_public", request)

    result = web.fetch_page("https://public.example/redirect")

    assert result.startswith("Refused:")
    assert len(requests) == 1
    assert requests[0]["host"] == "public.example"


def test_http_and_https_connections_use_pinned_address(monkeypatch):
    calls = []
    tls_hosts = []

    class FakeSocket:
        def close(self):
            pass

    class FakeTLSContext:
        verify_mode = web.ssl.CERT_REQUIRED
        check_hostname = True
        post_handshake_auth = None

        def set_alpn_protocols(self, protocols):
            pass

        def wrap_socket(self, sock, *, server_hostname):
            tls_hosts.append(server_hostname)
            return sock

    fake_socket = FakeSocket()
    monkeypatch.setattr(
        web.socket,
        "create_connection",
        lambda address, timeout: calls.append((address, timeout)) or fake_socket,
    )
    monkeypatch.setattr(web.ssl, "create_default_context", FakeTLSContext)

    http = web._PinnedHTTPConnection("guide.example", 80, "93.184.216.34", 3.0)
    http.connect()
    http.close()
    https = web._PinnedHTTPSConnection("guide.example", 443, "93.184.216.34", 3.0)
    https.connect()
    https.close()

    assert calls == [(("93.184.216.34", 80), 3.0), (("93.184.216.34", 443), 3.0)]
    assert tls_hosts == ["guide.example"]
