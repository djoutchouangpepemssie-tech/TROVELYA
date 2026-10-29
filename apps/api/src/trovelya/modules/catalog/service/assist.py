"""AI help to list an item, "Vendre en 30 s" (P2-T06a1c, plan Q45). Never commits; the AI
service logs and commits each call itself (it counts even if it fails).

From 1 to 4 of the member's photos, the provider proposes a title, a category, a brand, a
condition, attributes and a caption. The server never invents a value and keeps only what the
catalogue allows: a category that is not an active leaf goes, with its attributes; an attribute
the category refuses goes; a condition or a brand the category does not take goes. The member
decides from there (W09)."""

from typing import Any
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.ai import service as ai
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.models import ItemCondition
from trovelya.modules.catalog.schemas import AssistOut, BrandName, Caption, Title
from trovelya.modules.catalog.service.categories import LOCALE
from trovelya.modules.catalog.service.draft_rules import brand_slug, valid_attributes
from trovelya.modules.media.service import listing_photos
from trovelya.shared.clock import Clock

_TITLE: TypeAdapter[str] = TypeAdapter(Title)
_BRAND: TypeAdapter[str] = TypeAdapter(BrandName)
_CAPTION: TypeAdapter[str] = TypeAdapter(Caption)
CONFIDENT_OF = ("title", "category", "brand", "condition", "attributes", "caption")


def _valid(adapter: TypeAdapter[str], value: str | None) -> str | None:
    try:
        return None if value is None else adapter.validate_python(value)
    except ValidationError:
        return None


def _condition(value: str | None, leaf: Row[Any] | None) -> ItemCondition | None:
    if value not in set(ItemCondition):
        return None
    allowed = leaf.allowed_conditions if leaf is not None else None
    return ItemCondition(value) if not allowed or value in allowed else None


def _brand(value: str | None, leaf: Row[Any] | None) -> str | None:
    name = _valid(_BRAND, value)
    if name is None or brand_slug(name) is None:
        return None
    return None if leaf is not None and leaf.brand_policy == "none" else name


async def _kept(
    db: AsyncSession,
    call_id: UUID,
    suggestion: ai.ListingSuggestion,
    leaves: dict[str, Row[Any]],
    clock: Clock,
) -> AssistOut:
    leaf = leaves.get(suggestion.category_key or "")
    kept: dict[str, Any] = {
        "suggestion_id": call_id,
        "title": _valid(_TITLE, suggestion.title),
        "category": {"key": leaf.key, "name": leaf.names[LOCALE]} if leaf else None,
        "brand": _brand(suggestion.brand, leaf),
        "condition": _condition(suggestion.condition, leaf),
        "attributes": (
            await valid_attributes(db, leaf.id, dict(suggestion.attributes), clock) if leaf else {}
        ),
        "caption": _valid(_CAPTION, suggestion.caption),
        "price_range": None,
    }
    shown = {name for name in CONFIDENT_OF if kept[name] not in (None, {})}
    kept["confidence"] = {k: v for k, v in suggestion.confidence.items() if k in shown}
    return AssistOut.model_validate(kept)


async def assist(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: ai.AIProvider,
    *,
    member_id: UUID,
    media_ids: list[UUID],
    verticals: bool,
    clock: Clock,
) -> AssistOut:
    """404 for a photo not the member's, 409 for one not processed, 429 `ai_limit` over the
    cap, 503 `ai_unavailable` when the provider fails."""
    async with sessionmaker() as db:  # refused here, before any call: never counted (Q45)
        await listing_photos.check_listing_photos(db, owner_id=member_id, media_ids=media_ids)
        images = await listing_photos.assist_variants(db, media_ids)
        if len(images) != len(media_ids):  # a photo taken down by the moderation (Q40)
            raise AppError(ErrorCode.MEDIA_NOT_READY, 409)
        rows = await repository.active_categories(db, verticals=verticals)
        leaves = {row.key: row for row in rows if row.is_leaf}
    call_id = await ai.reserve_call(
        sessionmaker, provider, user_id=member_id, media_ids=media_ids, now=clock.now()
    )
    suggestion = await ai.suggest(
        sessionmaker,
        provider,
        call_id=call_id,
        images=[ai.ImageRef(**image) for image in images],
        leaves=[ai.Leaf(key=row.key, name=row.names[LOCALE]) for row in leaves.values()],
    )
    async with sessionmaker() as db:
        return await _kept(db, call_id, suggestion, leaves, clock)
