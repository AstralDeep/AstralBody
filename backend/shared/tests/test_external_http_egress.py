"""Unit tests for shared.external_http SSRF / egress guard."""
import socket
from unittest.mock import patch

import pytest

from shared.external_http import (
    EgressBlockedError,
    ServiceUnreachableError,
    validate_egress_url,
)


def _fake_resolve(host_to_addr):
    """Return a stand-in for socket.getaddrinfo that maps hosts to a fixed IP."""
    def _resolver(host, *args, **kwargs):
        if host not in host_to_addr:
            raise socket.gaierror(f"unknown host: {host}")
        addr = host_to_addr[host]
        family = socket.AF_INET6 if ":" in addr else socket.AF_INET
        sockaddr = (addr, 0, 0, 0) if family == socket.AF_INET6 else (addr, 0)
        return [(family, socket.SOCK_STREAM, 6, "", sockaddr)]
    return _resolver


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",
        "file:///etc/passwd",
        "gopher://example.com/",
        "javascript:alert(1)",
    ],
)
def test_rejects_non_http_schemes(url: str) -> None:
    with pytest.raises(EgressBlockedError):
        validate_egress_url(url)


def test_rejects_loopback_v4() -> None:
    with patch("socket.getaddrinfo", _fake_resolve({"localhost": "127.0.0.1"})):
        with pytest.raises(EgressBlockedError, match="loopback|private"):
            validate_egress_url("http://localhost:8080/")


def test_rejects_loopback_v6() -> None:
    with patch("socket.getaddrinfo", _fake_resolve({"localhost": "::1"})):
        with pytest.raises(EgressBlockedError):
            validate_egress_url("http://localhost/")


@pytest.mark.parametrize("addr", ["10.0.0.5", "172.16.42.1", "192.168.1.7"])
def test_rejects_rfc1918(addr: str) -> None:
    with patch("socket.getaddrinfo", _fake_resolve({"internal.local": addr})):
        with pytest.raises(EgressBlockedError):
            validate_egress_url("http://internal.local/")


def test_rejects_link_local_metadata() -> None:
    with patch("socket.getaddrinfo", _fake_resolve({"metadata": "169.254.169.254"})):
        with pytest.raises(EgressBlockedError):
            validate_egress_url("http://metadata/")


def test_allows_public_address() -> None:
    with patch("socket.getaddrinfo", _fake_resolve({"public.example.com": "8.8.8.8"})):
        validate_egress_url("https://public.example.com/")  # should not raise


def test_allow_list_overrides_block() -> None:
    with patch("socket.getaddrinfo", _fake_resolve({"internal.local": "10.0.0.5"})):
        validate_egress_url(
            "http://internal.local/",
            allowed_private_hosts=["internal.local"],
        )  # should not raise


def test_dns_failure_blocks_egress() -> None:
    def _failing(*_a, **_kw):
        raise socket.gaierror("Name or service not known")
    with patch("socket.getaddrinfo", _failing):
        with pytest.raises(EgressBlockedError):
            validate_egress_url("https://does-not-resolve.example/")


def test_url_without_host_is_blocked() -> None:
    with pytest.raises(EgressBlockedError):
        validate_egress_url("https:///path-only")
