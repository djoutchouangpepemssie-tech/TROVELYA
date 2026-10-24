"""Following and blocking members (P1-T10, Q14).

Blocking removes the follows both ways and prevents following again, in either direction. The
blocked person must not learn it: following someone who blocked you answers 404, exactly like
an unknown account, and the public profile stays visible.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.identity import repository
from trovelya.shared.clock import Clock


async def _target(db: AsyncSession, *, me: UUID, target: UUID) -> None:
    if target == me:
        raise AppError(ErrorCode.VALIDATION_ERROR, 422)
    if not await repository.social_target_exists(db, target):
        raise AppError(ErrorCode.NOT_FOUND, 404)


async def follow(db: AsyncSession, *, me: UUID, target: UUID, clock: Clock) -> None:
    await _target(db, me=me, target=target)
    if await repository.blocked_either_way(db, me, target):
        raise AppError(ErrorCode.NOT_FOUND, 404)
    await repository.follow(db, follower=me, followee=target, now=clock.now())


async def unfollow(db: AsyncSession, *, me: UUID, target: UUID) -> None:
    await repository.unfollow(db, follower=me, followee=target)


async def block(db: AsyncSession, *, me: UUID, target: UUID, clock: Clock) -> None:
    await _target(db, me=me, target=target)
    await repository.block(db, blocker=me, blocked=target, now=clock.now())


async def unblock(db: AsyncSession, *, me: UUID, target: UUID) -> None:
    await repository.unblock(db, blocker=me, blocked=target)


async def blocks(db: AsyncSession, me: UUID) -> list[Row[Any]]:
    return await repository.list_blocks(db, me)


async def relationship(db: AsyncSession, *, viewer: UUID, target: UUID) -> dict[str, bool]:
    row = await repository.relationship(db, viewer=viewer, target=target)
    return {"following": bool(row.following), "blocking": bool(row.blocking)}
