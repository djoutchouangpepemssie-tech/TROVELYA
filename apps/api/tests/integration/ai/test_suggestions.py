"""Calls to the AI provider (P2-T06a, plan Q45): each one logged before it leaves, counted
over 24 rolling hours whatever its outcome, refused when it costs more than 2 cents."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

from tests.conftest import make_settings
from tests.integration.catalog.test_drafts import Session
from tests.integration.identity.test_profile import make_account
from trovelya.core.errors import AppError
from trovelya.modules.ai.adapters.provider import FakeAIProvider, ImageRef, Leaf, ProviderAnswer
from trovelya.modules.ai.service import reserve_call, suggest
from trovelya.shared.ids import new_id

IMAGES = [ImageRef(key="k", format="webp", width=1080)]
LEAVES = [Leaf(key="mode.femme.robes", name="Robes")]


class Saying(FakeAIProvider):
    """Answers `changes` over the fake suggestion, at `cost` micro-euros."""

    def __init__(self, cost: int = 500, **changes: Any) -> None:
        super().__init__()
        self.cost, self.changes = cost, changes

    async def suggest_listing(
        self, images: Sequence[ImageRef], leaves: Sequence[Leaf]
    ) -> ProviderAnswer:
        answer = await super().suggest_listing(images, leaves)
        return ProviderAnswer(output=answer.output | self.changes, cost_microeur=self.cost)


class Down(FakeAIProvider):
    async def suggest_listing(
        self, images: Sequence[ImageRef], leaves: Sequence[Leaf]
    ) -> ProviderAnswer:
        raise TimeoutError


async def calls(sessionmaker: Session, user_id: UUID) -> list[dict[str, Any]]:
    async with sessionmaker() as db:
        rows = await db.execute(
            text(
                "SELECT model, outcome, suggestion, media_ids, latency_ms, cost_microeur"
                " FROM ai_listing_suggestions WHERE user_id = :u ORDER BY created_at, id"
            ),
            {"u": user_id},
        )
        return [dict(row) for row in rows.mappings()]


async def _reserve(sessionmaker: Session, user_id: UUID, now: datetime) -> UUID:
    async with sessionmaker() as db:
        call_id = await reserve_call(
            db, user_id=user_id, media_ids=[new_id()], model="fake-assist-v1", now=now
        )
        await db.commit()
    return call_id


async def _call(sessionmaker: Session, provider: FakeAIProvider) -> tuple[UUID, Any]:
    """A member's call, and what came of it: the suggestion or the error."""
    member = await make_account(sessionmaker, completed=True)
    call_id = await _reserve(sessionmaker, member.id, datetime.now(UTC))
    try:
        found: Any = await suggest(
            sessionmaker, provider, call_id=call_id, images=IMAGES, leaves=LEAVES
        )
    except AppError as error:
        found = error
    return member.id, found


async def test_assist_daily_limit(sessionmaker: Session) -> None:
    """Q45: 20 calls over 24 rolling hours; the oldest leaving the window frees one."""
    member = await make_account(sessionmaker, completed=True)
    now = datetime.now(UTC)
    await _reserve(sessionmaker, member.id, now - timedelta(hours=48))  # out of the window
    for minutes in range(20):
        await _reserve(sessionmaker, member.id, now - timedelta(hours=23, minutes=-minutes))
    with pytest.raises(AppError) as refused:
        await _reserve(sessionmaker, member.id, now)
    assert (refused.value.status, refused.value.code) == (429, "ai_limit")
    assert refused.value.headers == {"Retry-After": "3600"}  # the oldest of 23 hours leaves
    assert len(await calls(sessionmaker, member.id)) == 21  # the refused one was never made
    await _reserve(sessionmaker, member.id, now + timedelta(hours=1, seconds=1))


async def test_assist_cost_cap(sessionmaker: Session) -> None:
    """A suggestion over 2 cents is never shown; it is logged with its cost."""
    member, found = await _call(sessionmaker, Saying(cost=20_001))
    assert (found.status, found.code) == (429, "ai_limit")
    [call] = await calls(sessionmaker, member)
    assert (call["outcome"], call["cost_microeur"]) == ("over_cost", 20_001)
    _, found = await _call(sessionmaker, Saying(cost=20_000))
    assert found.title == "Robe en lin bleue"


async def test_assist_logged_with_latency_and_cost(sessionmaker: Session) -> None:
    member, found = await _call(sessionmaker, FakeAIProvider())
    assert found.category_key == "mode.femme.robes"
    [call] = await calls(sessionmaker, member)
    assert (call["model"], call["outcome"], call["cost_microeur"]) == ("fake-assist-v1", "ok", 500)
    assert call["latency_ms"] >= 0 and len(call["media_ids"]) == 1
    assert call["suggestion"]["category_key"] == "mode.femme.robes"  # what the provider said


@pytest.mark.parametrize(
    ("provider", "outcome"),
    [
        (Down(), "failed"),
        (Saying(title=["not", "a", "title"]), "invalid"),
        (Saying(category_key=42), "invalid"),
        (Saying(confidence={"title": 2}), "invalid"),
    ],
)
async def test_provider_failure_logged(
    sessionmaker: Session, provider: FakeAIProvider, outcome: str
) -> None:
    """Down, or an answer not of the schema: 503, logged, and it counts (Q45)."""
    member, found = await _call(sessionmaker, provider)
    assert (found.status, found.code) == (503, "ai_unavailable")
    assert [call["outcome"] for call in await calls(sessionmaker, member)] == [outcome]


async def test_answer_beyond_the_schema_ignored(sessionmaker: Session) -> None:
    """A field the model added is dropped; a missing field is none."""
    member, found = await _call(sessionmaker, Saying(price=1, caption=None))
    assert found.caption is None and "price" not in found.model_dump()
    [call] = await calls(sessionmaker, member)
    assert "price" not in call["suggestion"]


@pytest.mark.parametrize("environment", ["preview", "staging", "production"])
def test_fake_provider_refused_outside_development(environment: str) -> None:
    with pytest.raises(ValueError, match="AI_PROVIDER"):
        make_settings(env=environment, ai_provider="fake")
