"""Registries of GDPR exporters (ADR-0016) and erasers (P1-T09b).

Each module registers a function returning the person's data it holds (the export archive has
one key per exporter) and one deleting or anonymising it when the account is erased. A new
phase that stores personal data registers both.
"""

from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

Exporter = Callable[[AsyncSession, UUID], Awaitable[dict[str, Any]]]
Eraser = Callable[[AsyncSession, UUID], Awaitable[None]]

_EXPORTERS: dict[str, Exporter] = {}
_ERASERS: dict[str, Eraser] = {}


def register_exporter(name: str, fn: Exporter) -> None:
    """Idempotent for the same function; a second, different exporter under a name is a bug."""
    if _EXPORTERS.get(name, fn) is not fn:
        raise ValueError(f"exporter {name!r} already registered")
    _EXPORTERS[name] = fn


def registered_exporters() -> Mapping[str, Exporter]:
    return MappingProxyType(_EXPORTERS)


def register_eraser(name: str, fn: Eraser) -> None:
    """Runs inside the erasure transaction, before the account itself is anonymised."""
    if _ERASERS.get(name, fn) is not fn:
        raise ValueError(f"eraser {name!r} already registered")
    _ERASERS[name] = fn


def registered_erasers() -> Mapping[str, Eraser]:
    return MappingProxyType(_ERASERS)
