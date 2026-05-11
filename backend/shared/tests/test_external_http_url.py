"""Unit tests for shared.external_http URL normalization."""
import pytest

from shared.external_http import EgressBlockedError, normalize_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("classify.ai.uky.edu", "https://classify.ai.uky.edu"),
        ("classify.ai.uky.edu/", "https://classify.ai.uky.edu"),
        ("https://classify.ai.uky.edu/", "https://classify.ai.uky.edu"),
        ("HTTPS://CLASSIFY.AI.UKY.EDU/", "https://classify.ai.uky.edu"),
        ("http://forecaster.ai.uky.edu", "http://forecaster.ai.uky.edu"),
        ("https://example.com:8443", "https://example.com:8443"),
        ("https://example.com:8443/", "https://example.com:8443"),
        ("https://example.com/api", "https://example.com/api"),
        ("https://example.com/api/", "https://example.com/api"),
        ("https://example.com/api/v2/widgets", "https://example.com/api/v2/widgets"),
        ("https://example.com/?token=x", "https://example.com?token=x"),
        # IPv6 literal (passes through; SSRF guard catches loopback later)
        ("https://[2001:db8::1]/", "https://[2001:db8::1]"),
        # Whitespace trimmed
        ("  https://example.com/  ", "https://example.com"),
    ],
)
def test_normalize_url_canonicalizes(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_normalize_url_rejects_empty(raw) -> None:
    with pytest.raises(EgressBlockedError):
        normalize_url(raw)
