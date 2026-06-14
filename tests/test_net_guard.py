"""Tests for the SSRF guard protecting /api/read."""

from __future__ import annotations

from services import net_guard


def test_rejects_non_http_schemes():
    assert net_guard.is_safe_public_url("file:///etc/passwd") is False
    assert net_guard.is_safe_public_url("ftp://example.com/x") is False
    assert net_guard.is_safe_public_url("gopher://example.com") is False


def test_rejects_empty_or_bad_input():
    assert net_guard.is_safe_public_url("") is False
    assert net_guard.is_safe_public_url(None) is False  # type: ignore[arg-type]
    assert net_guard.is_safe_public_url("not a url") is False


def test_rejects_loopback_and_private_literals():
    assert net_guard.is_safe_public_url("http://127.0.0.1/admin") is False
    assert net_guard.is_safe_public_url("http://localhost:8080") is False
    assert net_guard.is_safe_public_url("http://10.0.0.5/") is False
    assert net_guard.is_safe_public_url("http://192.168.1.1/") is False
    assert net_guard.is_safe_public_url("http://172.16.0.1/") is False


def test_rejects_cloud_metadata_address():
    # The classic SSRF target — link-local metadata endpoint.
    assert net_guard.is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False


def test_allows_public_host(monkeypatch):
    # Stub DNS so the test never hits the network: resolve to a public IP.
    def fake_getaddrinfo(host, port, *a, **kw):
        return [(2, 1, 6, "", ("93.184.216.34", port or 80))]

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake_getaddrinfo)
    assert net_guard.is_safe_public_url("https://vnexpress.net/some-article") is True


def test_rejects_when_any_resolved_ip_is_private(monkeypatch):
    # DNS-rebinding style: name resolves to both a public and a private IP.
    def fake_getaddrinfo(host, port, *a, **kw):
        return [
            (2, 1, 6, "", ("93.184.216.34", port or 80)),
            (2, 1, 6, "", ("10.0.0.5", port or 80)),
        ]

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake_getaddrinfo)
    assert net_guard.is_safe_public_url("https://evil.example/x") is False


def test_rejects_unresolvable_host(monkeypatch):
    def boom(*a, **kw):
        raise net_guard.socket.gaierror("no such host")

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", boom)
    assert net_guard.is_safe_public_url("https://does-not-exist.invalid/") is False
