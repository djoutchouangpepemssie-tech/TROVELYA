"""Registry of GDPR exporters (ADR-0016).

Each module registers a function returning the person's data it holds; the export archive has
one key per exporter. A new phase that stores personal data registers its own.
"""

from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

Exporter = Callable[[AsyncSession, UUID], Awaitable[dict[str, Any]]]

_EXPORTERS: dict[str, Exporter] = {}


def register_exporter(name: str, fn: Exporter) -> None:
    """Idempotent for the same function; a second, different exporter under a name is a bug."""
    if _EXPORTERS.get(name, fn) is not fn:
        raise ValueError(f"exporter {name!r} already registered")
    _EXPORTERS[name] = fn


def registered_exporters() -> Mapping[str, Exporter]:
    return MappingProxyType(_EXPORTERS)
