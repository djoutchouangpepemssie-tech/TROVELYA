"""Public service of the AI module (P2-T06a, plan Q45): the only entry point for other modules.

Every call to the provider is logged and counts in the member's cap over 24 rolling hours,
whatever comes of it (a call still pending counts too). Both functions commit, by exception to
the rule of the services, so that no transaction is held while the provider answers and a
failed call is never rolled back with the request: `reserve_call` counts and logs the call,
under a lock on the member, and commits before it leaves; `suggest` calls the provider and
records how it went in a transaction of its own. A suggestion is shown only if the answer is
of the schema and its announced cost an integer within `ai.assist_max_cost_microeur`."""

import asyncio
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.config import Settings
from trovelya.core.db import commit
from trovelya.core.errors import AppError, ErrorCode
from trovelya.core.gdpr import register_eraser, register_exporter
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

PROVIDER_TIMEOUT_S = 30  # a safety net: each adapter sets its own, shorter timeout
MAX_COST_MICROEUR = 2**31 - 1  # the column's bound; a cost beyond is not believed

Session = async_sessionmaker[AsyncSession]


def unavailable() -> AppError:
    return AppError(ErrorCode.AI_UNAVAILABLE, 503)


async def reserve_call(
    sessionmaker: Session,
    provider: AIProvider,
    *,
    user_id: UUID,
    media_ids: list[UUID],
    now: datetime,
) -> UUID:
    """The call, logged and committed before it leaves; 429 `ai_limit` with `Retry-After`
    once the member made `ai.assist_per_day` calls over the last 24 hours (Q45)."""
    async with sessionmaker() as db:
        await repository.lock_member(db, user_id)
        limit = await repository.setting_int(db, "ai.assist_per_day")
        wait = retry_after(await repository.calls_since(db, user_id, now - DAY), limit, now)
        if wait is not None:
            raise AppError(ErrorCode.AI_LIMIT, 429, headers={"Retry-After": str(wait)})
        call_id = new_id()
        await repository.reserve(
            db, call_id=call_id, user_id=user_id, media_ids=media_ids, model=provider.model, now=now
        )
        await commit(db)
    return call_id


async def _finish(
    sessionmaker: Session,
    call_id: UUID,
    outcome: str,
    *,
    started: float,
    suggestion: dict[str, Any] | None = None,
    cost: int | None = None,
) -> None:
    latency_ms = round((time.monotonic() - started) * 1000)
    async with sessionmaker() as db:
        finished = await repository.finish(
            db,
            call_id,
            outcome=outcome,
            suggestion=suggestion or {},
            latency_ms=latency_ms,
            cost_microeur=cost,
        )
        await commit(db)
    if not finished:  # not reserved, or already finished: a bug of the caller
        logger.error("ai.call_not_pending", call_id=str(call_id), outcome=outcome)


def _cost(value: object) -> int | None:
    """The announced cost if it is believable: a non-negative integer within the column."""
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_COST_MICROEUR:
        return value
    return None


async def _ask(
    sessionmaker: Session,
    provider: AIProvider,
    call_id: UUID,
    started: float,
    images: Sequence[ImageRef],
    leaves: Sequence[Leaf],
) -> ListingSuggestion:
    try:
        async with asyncio.timeout(PROVIDER_TIMEOUT_S):
            answer = await provider.suggest_listing(images, leaves)
    except Exception:
        logger.exception("ai.provider_failed", call_id=str(call_id))
        await _finish(sessionmaker, call_id, "failed", started=started)
        raise unavailable() from None
    cost = _cost(answer.cost_microeur)
    try:
        suggestion = ListingSuggestion.model_validate(answer.output)
    except ValidationError:
        logger.warning("ai.answer_invalid", call_id=str(call_id))
        await _finish(sessionmaker, call_id, "invalid", started=started, cost=cost)
        raise unavailable() from None
    async with sessionmaker() as db:
        max_cost = await repository.setting_int(db, "ai.assist_max_cost_microeur")
    outcome = "ok" if cost is not None and cost <= max_cost else "over_cost"
    kept = suggestion.model_dump()
    await _finish(sessionmaker, call_id, outcome, started=started, suggestion=kept, cost=cost)
    if outcome == "over_cost":  # an unbelievable cost is taken as too dear
        logger.warning("ai.over_cost", call_id=str(call_id), cost=answer.cost_microeur)
        raise AppError(ErrorCode.AI_LIMIT, 429)
    return suggestion


async def suggest(
    sessionmaker: Session,
    provider: AIProvider,
    *,
    call_id: UUID,
    images: Sequence[ImageRef],
    leaves: Sequence[Leaf],
) -> ListingSuggestion:
    """What the provider said, of the schema; 503 `ai_unavailable` when it failed or answered
    something else, 429 `ai_limit` when it cost too much. Cancelled meanwhile (a shutdown), the
    call is still recorded as failed."""
    started = time.monotonic()
    try:
        return await _ask(sessionmaker, provider, call_id, started, images, leaves)
    except AppError:
        raise
    except asyncio.CancelledError:
        # A row already finished is left as it is (`finish` touches only a pending one).
        await asyncio.shield(_finish(sessionmaker, call_id, "failed", started=started))
        raise
    except Exception:  # the log could not be written (a database failure): never a 500 page
        logger.exception("ai.log_failed", call_id=str(call_id))
        raise unavailable() from None


async def _export(db: AsyncSession, user_id: UUID, settings: Settings) -> dict[str, Any]:
    """Q46: every call of the member, with what the AI said (right of access)."""
    return {"ai_listing_suggestions": await repository.export_calls(db, user_id)}


register_exporter("ai", _export)
register_eraser("ai", repository.erase_calls)  # Q46: gone with the account
