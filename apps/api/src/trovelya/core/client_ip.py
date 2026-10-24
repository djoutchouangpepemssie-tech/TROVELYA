"""Client IP and country behind the same-origin web relay (ADR-0015).

The browser only talks to the web origin; its relay (`apps/web/app/api/[...path]/route.ts`)
calls the API from Vercel. The relay sends the visitor's IP and country in `x-trv-client-ip`
and `x-trv-client-country`, authenticated by `x-trv-proxy-secret` (`PROXY_SHARED_SECRET`).
Those headers are believed only when the secret matches. Otherwise the API falls back to
`X-Real-IP`, which Railway's edge overwrites with the connecting address, then to the TCP
peer. `X-Forwarded-For` is never believed: a client can prepend anything to it.
"""

import hmac
import ipaddress
import re

from starlette.types import Scope

PROXY_SECRET_HEADER = "x-trv-proxy-secret"  # noqa: S105 — header name, not a secret
CLIENT_IP_HEADER = "x-trv-client-ip"
CLIENT_COUNTRY_HEADER = "x-trv-client-country"
_COUNTRY = re.compile(r"^[A-Z]{2}$")


def _header(scope: Scope, name: str) -> str | None:
    for key, value in scope.get("headers", []):
        if key.decode("latin-1") == name:
            return value.decode("latin-1").strip()
    return None


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _from_relay(scope: Scope, proxy_secret: str) -> bool:
    supplied = _header(scope, PROXY_SECRET_HEADER)
    return supplied is not None and hmac.compare_digest(supplied.encode(), proxy_secret.encode())


def client_ip(scope: Scope, *, proxy_secret: str) -> str:
    if _from_relay(scope, proxy_secret):
        relayed = _valid_ip(_header(scope, CLIENT_IP_HEADER))
        if relayed:
            return relayed
    real_ip = _valid_ip(_header(scope, "x-real-ip"))
    if real_ip:
        return real_ip
    client = scope.get("client")
    return client[0] if client else "unknown"


def client_country(scope: Scope, *, proxy_secret: str) -> str | None:
    """ISO 3166-1 alpha-2 code from Vercel's geolocation, only through the relay."""
    if not _from_relay(scope, proxy_secret):
        return None
    country = _header(scope, CLIENT_COUNTRY_HEADER)
    return country if country and _COUNTRY.match(country) else None
