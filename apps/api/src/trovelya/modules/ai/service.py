"""Public service of the AI module (P2-T06a, plan Q45): the only entry point for other modules.

Every call to the provider is logged and counts in the member's cap over 24 rolling hours:
`reserve_call` counts and logs it before it leaves, under a lock on the member, in the caller's
transaction; `suggest` calls the provider outside any transaction (it may take seconds) and
records how it went in a transaction of its own, which it commits: a call that failed still
counts. A suggestion is shown only if its answer is of the schema and its cost within
`ai.assist_max_cost_microeur`."""

import asyncio
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.db import commit
from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.ai import repository
from trovelya.modules.ai.adapters.provider import AIProvider, ImageRef, Leaf
from trovelya.modules.ai.schemas import ListingSuggestion
from trovelya.shared.ids import new_id
from trovelya.shared.quota import DAY, retry_after

__all__ = [
    "AIProvider",
    "ImageRef",
    "Leaf",
    "ListingSuggestion",
    "reserve_call",
    "suggest",
    "unavailable",
]

logger = structlog.get_logger(__name__)

PROVIDER_TIMEOUT_S = 30


def unavailable() -> AppError:
    return AppError(ErrorCode.AI_UNAVAILABLE, 503)


async def reserve_call(
    db: AsyncSession, *, user_id: UUID, media_ids: list[UUID], model: str, now: datetime
) -> UUID:
    """The call, logged before it leaves; 429 `ai_limit` with `Retry-After` once the member
    made `ai.assist_per_day` calls over the last 24 hours (Q45)."""
    await repository.lock_member(db, user_id)
    limit = await repository.setting_int(db, "ai.assist_per_day")
    wait = retry_after(await repository.calls_since(db, user_id, now - DAY), limit, now)
    if wait is not None:
        raise AppError(ErrorCode.AI_LIMIT, 429, headers={"Retry-After": str(wait)})
    call_id = new_id()
    await repository.reserve(
        db, call_id=call_id, user_id=user_id, media_ids=media_ids, model=model, now=now
    )
    return call_id


async def _finish(
    sessionmaker: async_sessionmaker[AsyncSession],
    call_id: UUID,
    outcome: str,
    *,
    started: float,
    suggestion: dict[str, Any] | None = None,
    cost: int | None = None,
) -> None:
    latency_ms = round((time.monotonic() - started) * 1000)
    async with sessionmaker() as db:
        await repository.finish(
            db,
            call_id,
            outcome=outcome,
            suggestion=suggestion or {},
            latency_ms=latency_ms,
            cost_microeur=cost,
        )
        await commit(db)


async def suggest(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: AIProvider,
    *,
    call_id: UUID,
    images: Sequence[ImageRef],
    leaves: Sequence[Leaf],
) -> ListingSuggestion:
    """What the provider said, of the schema; 503 `ai_unavailable` when it failed or answered
    something else, 429 `ai_limit` when it cost too much."""
    started = time.monotonic()
    try:
        async with asyncio.timeout(PROVIDER_TIMEOUT_S):
            answer = await provider.suggest_listing(images, leaves)
    except Exception:
        logger.exception("ai.provider_failed", call_id=str(call_id))
        await _finish(sessionmaker, call_id, "failed", started=started)
        raise unavailable() from None
    try:
        suggestion = ListingSuggestion.model_validate(answer.output)
    except ValidationError:
        logger.warning("ai.answer_invalid", call_id=str(call_id))
        await _finish(sessionmaker, call_id, "invalid", started=started, cost=answer.cost_microeur)
        raise unavailable() from None
    async with sessionmaker() as db:
        max_cost = await repository.setting_int(db, "ai.assist_max_cost_microeur")
    outcome = "ok" if answer.cost_microeur <= max_cost else "over_cost"
    kept = suggestion.model_dump()
    await _finish(
        sessionmaker, call_id, outcome, started=started, suggestion=kept, cost=answer.cost_microeur
    )
    if outcome == "over_cost":
        logger.warning("ai.over_cost", call_id=str(call_id), cost=answer.cost_microeur)
        raise AppError(ErrorCode.AI_LIMIT, 429)
    return suggestion
