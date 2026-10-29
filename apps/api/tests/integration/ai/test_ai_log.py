"""The log of the AI calls (P2-T06a1a, Q46) and the shape of a provider's answer: what does
not fit the schema is refused, so that what is kept can always be stored as JSONB."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from tests.conftest import make_settings
from tests.integration.catalog.test_drafts import Session
from tests.integration.identity.test_profile import make_account
from trovelya.core.gdpr import registered_erasers, registered_exporters
from trovelya.modules.ai.adapters.provider import FakeAIProvider
from trovelya.modules.ai.schemas import ListingSuggestion
from trovelya.modules.ai.tasks import purge_old_calls
from trovelya.shared.clock import FixedClock
from trovelya.shared.ids import new_id


async def test_calls_exported_and_erased(sessionmaker: Session) -> None:
    """Q46: in the member's GDPR export, gone with the account."""
    member = await make_account(sessionmaker, completed=True)
    answer = await FakeAIProvider().suggest_listing([], [])
    async with sessionmaker() as db:
        await db.execute(
            text(
                "INSERT INTO ai_listing_suggestions (id, user_id, media_ids, model, outcome,"
                " suggestion) VALUES (:id, :u, ARRAY[CAST(:m AS uuid)], 'fake', 'ok',"
                " CAST(:s AS jsonb))"
            ),
            {"id": new_id(), "u": member.id, "m": new_id(), "s": json.dumps(answer.output)},
        )
        export = await registered_exporters()["ai"](db, member.id, make_settings())
        await registered_erasers()["ai"](db, member.id)
        left = await db.scalar(
            text("SELECT count(*) FROM ai_listing_suggestions WHERE user_id = :u"),
            {"u": member.id},
        )
        await db.commit()
    [row] = export["ai_listing_suggestions"]
    assert (row["outcome"], row["suggestion"]["title"]) == ("ok", "Robe en lin bleue")
    assert left == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ["not", "a", "title"]},
        {"category_key": 42},
        {"confidence": {"title": 2}},
        {"attributes": {"weight": float("nan")}},  # never stored in JSONB
        {"title": "Robe\x00 bleue"},  # NUL, refused by PostgreSQL
        {"attributes": {"x" * 65: 1}},
        {"title": ""},
    ],
)
async def test_answer_not_of_the_schema_refused(changes: dict[str, Any]) -> None:
    answer = await FakeAIProvider().suggest_listing([], [])
    with pytest.raises(ValidationError):
        ListingSuggestion.model_validate(answer.output | changes)


def test_answer_beyond_the_schema_ignored() -> None:
    """A field the model added is dropped; a missing field is none."""
    found = ListingSuggestion.model_validate({"title": "Robe", "price": 1})
    assert found.caption is None and "price" not in found.model_dump()


@pytest.mark.parametrize("environment", ["preview", "staging", "production"])
def test_fake_provider_refused_outside_development(environment: str) -> None:
    with pytest.raises(ValueError, match="AI_PROVIDER"):
        make_settings(env=environment, ai_provider="fake")


async def test_calls_purged_after_a_year(sessionmaker: Session) -> None:
    """Q46: a call is kept 365 days ([PARAM] retention.ai_suggestion_days), then erased by the
    daily purge; a younger one stays."""
    member = await make_account(sessionmaker, completed=True)
    now = datetime(2026, 10, 29, 12, tzinfo=UTC)
    ages = {"old": timedelta(days=365, microseconds=1), "edge": timedelta(days=365)}
    ids = {name: new_id() for name in ages}
    async with sessionmaker() as db:
        for name, call_id in ids.items():
            await db.execute(
                text(
                    "INSERT INTO ai_listing_suggestions (id, user_id, media_ids, model,"
                    " created_at) VALUES (:id, :u, ARRAY[CAST(:m AS uuid)], 'fake', :at)"
                ),
                {"id": call_id, "u": member.id, "m": new_id(), "at": now - ages[name]},
            )
        await db.commit()
    assert await purge_old_calls(sessionmaker, clock=FixedClock(now)) >= 1
    async with sessionmaker() as db:
        left = set(
            await db.scalars(
                text("SELECT id FROM ai_listing_suggestions WHERE user_id = :u"), {"u": member.id}
            )
        )
    assert left == {ids["edge"]}  # exactly 365 days old: kept until the next purge
