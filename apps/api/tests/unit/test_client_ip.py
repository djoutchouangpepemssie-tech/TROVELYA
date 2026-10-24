"""Trusted client IP and country behind the same-origin web relay (ADR-0015, P1-T02a)."""

from starlette.types import Scope

from trovelya.core.client_ip import client_country, client_ip

SECRET = "s" * 48


def _scope(headers: dict[str, str], peer: str = "100.64.0.9") -> Scope:
    return {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 443),
    }


def test_proxy_headers_trusted_with_secret() -> None:
    scope = _scope(
        {
            "x-trv-proxy-secret": SECRET,
            "x-trv-client-ip": "203.0.113.7",
            "x-trv-client-country": "FR",
            "x-real-ip": "198.51.100.1",
        }
    )
    assert client_ip(scope, proxy_secret=SECRET) == "203.0.113.7"
    assert client_country(scope, proxy_secret=SECRET) == "FR"


def test_proxy_headers_ignored_without_secret() -> None:
    scope = _scope({"x-trv-client-ip": "203.0.113.7", "x-trv-client-country": "FR"})
    assert client_ip(scope, proxy_secret=SECRET) == "100.64.0.9"
    assert client_country(scope, proxy_secret=SECRET) is None


def test_proxy_headers_ignored_with_wrong_secret() -> None:
    scope = _scope(
        {
            "x-trv-proxy-secret": "t" * 48,
            "x-trv-client-ip": "203.0.113.7",
            "x-trv-client-country": "FR",
            "x-real-ip": "198.51.100.1",
        }
    )
    assert client_ip(scope, proxy_secret=SECRET) == "198.51.100.1"
    assert client_country(scope, proxy_secret=SECRET) is None


def test_x_forwarded_for_never_trusted() -> None:
    scope = _scope({"x-forwarded-for": "203.0.113.7, 10.0.0.1"})
    assert client_ip(scope, proxy_secret=SECRET) == "100.64.0.9"


def test_x_real_ip_fallback() -> None:
    """Railway's edge overwrites X-Real-IP with the connecting client (direct calls)."""
    assert client_ip(_scope({"x-real-ip": "2001:db8::1"}), proxy_secret=SECRET) == "2001:db8::1"


def test_invalid_ip_in_header_ignored() -> None:
    scope = _scope({"x-trv-proxy-secret": SECRET, "x-trv-client-ip": "not-an-ip"})
    assert client_ip(scope, proxy_secret=SECRET) == "100.64.0.9"
    assert client_ip(_scope({"x-real-ip": "999.1.1.1"}), proxy_secret=SECRET) == "100.64.0.9"


def test_country_must_be_two_letters() -> None:
    for value in ("fr", "FRA", "F1", ""):
        scope = _scope({"x-trv-proxy-secret": SECRET, "x-trv-client-country": value})
        assert client_country(scope, proxy_secret=SECRET) is None


def test_unknown_without_peer() -> None:
    scope: Scope = {"type": "http", "headers": [], "client": None}
    assert client_ip(scope, proxy_secret=SECRET) == "unknown"
