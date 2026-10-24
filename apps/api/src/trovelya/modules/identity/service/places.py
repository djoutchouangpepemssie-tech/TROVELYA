"""Shipping addresses and search zones of the signed-in member (P1-T06b).

- Another member's address or zone answers 404, as if it did not exist.
- At most one default shipping address; the first address becomes it.
- Exactly one default search zone while the member has any: the first one is the default,
  choosing another moves the role, deleting the default hands it to the oldest remaining zone.
- Search radius in {1, 2, 5, 10, 25, 50, 100} km, 5 km by default (local search first).
- Addresses are kept with `deleted_at` (future orders may point to them); zones are deleted.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity import repository
from trovelya.modules.identity.service.sessions import CurrentUser
from trovelya.shared.clock import Clock


def _not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, 404)


async def list_addresses(db: AsyncSession, *, user: CurrentUser) -> list[Row[Any]]:
    return await repository.list_addresses(db, user.id)


async def create_address(
    db: AsyncSession, *, user: CurrentUser, values: dict[str, Any]
) -> Row[Any]:
    first = await repository.count_addresses(db, user.id) == 0
    values = {**values, "is_default_shipping": values["is_default_shipping"] or first}
    if values["is_default_shipping"]:
        await repository.clear_default_address(db, user.id)
    return await repository.insert_address(db, user_id=user.id, values=values)


async def update_address(
    db: AsyncSession, *, user: CurrentUser, address_id: UUID, changes: dict[str, Any]
) -> Row[Any]:
    if changes.get("is_default_shipping"):
        await repository.clear_default_address(db, user.id)
    row = await repository.update_address(
        db, user_id=user.id, address_id=address_id, changes=changes
    )
    if row is None:
        # Also undoes the default cleared above: the request rolls back.
        raise _not_found()
    return row


async def delete_address(
    db: AsyncSession, *, user: CurrentUser, address_id: UUID, clock: Clock
) -> None:
    if not await repository.delete_address(
        db, user_id=user.id, address_id=address_id, now=clock.now()
    ):
        raise _not_found()


async def list_zones(db: AsyncSession, *, user: CurrentUser) -> list[Row[Any]]:
    return await repository.list_zones(db, user.id)


async def create_zone(db: AsyncSession, *, user: CurrentUser, values: dict[str, Any]) -> Row[Any]:
    first = await repository.count_zones(db, user.id) == 0
    is_default = bool(values.pop("is_default")) or first
    if is_default:
        await repository.clear_default_zone(db, user.id)
    return await repository.insert_zone(
        db, user_id=user.id, values={**values, "is_default": is_default}
    )


async def update_zone(
    db: AsyncSession, *, user: CurrentUser, zone_id: UUID, changes: dict[str, Any]
) -> Row[Any]:
    if not await repository.zone_exists(db, user_id=user.id, zone_id=zone_id):
        raise _not_found()
    if changes.get("is_default"):
        await repository.clear_default_zone(db, user.id)
    row = await repository.update_zone(db, user_id=user.id, zone_id=zone_id, changes=changes)
    if row is None:
        raise _not_found()
    return row


async def delete_zone(db: AsyncSession, *, user: CurrentUser, zone_id: UUID) -> None:
    was_default = await repository.delete_zone(db, user_id=user.id, zone_id=zone_id)
    if was_default is None:
        raise _not_found()
    if was_default:
        await repository.promote_oldest_zone(db, user.id)
