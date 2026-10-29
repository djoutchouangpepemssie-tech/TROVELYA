"""Registry of GDPR exporters (ADR-0016)."""

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import trovelya.modules.identity.service  # noqa: F401  # pyright: ignore[reportUnusedImport]  registers the exporter
from trovelya.core.config import Settings
from trovelya.core.gdpr import register_exporter, registered_exporters


async def _other(db: AsyncSession, user_id: UUID, settings: Settings) -> dict[str, Any]:
    return {}


def test_identity_is_registered_and_a_name_cannot_be_taken_twice() -> None:
    identity = registered_exporters()["identity"]
    register_exporter("identity", identity)  # same function: no-op
    with pytest.raises(ValueError, match="already registered"):
        register_exporter("identity", _other)
    assert registered_exporters()["identity"] is identity
