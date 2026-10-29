"""AI help to list an item, "Vendre en 30 s" (P2-T06a1c, plan Q45). Never commits; the AI
service logs and commits each call itself (it counts even if it fails).

From 1 to 4 of the member's photos, the provider proposes a title, a category, a brand, a
condition, attributes and a caption. The server never invents a value and keeps only what the
catalogue allows: a category that is not an active leaf goes, with its attributes; an attribute
the category refuses goes; a condition or a brand the category does not take goes. The member
decides from there (W09). A price range comes from the comparable listings online (Q44)."""

import asyncio
from typing import Any
from uuid import UUID

import structlog
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trovelya.core.errors import AppError, ErrorCode
from trovelya.modules.ai import service as ai
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.adapters.embedder import Embedder, checked_vector
from trovelya.modules.catalog.models import ItemCondition
from trovelya.modules.catalog.schemas import (
    AssistOut,
    BrandName,
    Caption,
    ListingDraftIn,
    Money,
    PriceRange,
    Title,
)
from trovelya.modules.catalog.service.categories import LOCALE
from trovelya.modules.catalog.service.draft_rules import brand_slug, valid_attributes
from trovelya.modules.catalog.service.embeddings import compose_text
from trovelya.modules.catalog.service.price_range import COMPARABLES, price_range
from trovelya.modules.media.service import listing_photos
from trovelya.shared.clock import Clock

logger = structlog.get_logger(__name__)
Session = async_sessionmaker[AsyncSession]

_TITLE: TypeAdapter[str] = TypeAdapter(Title)
_BRAND: TypeAdapter[str] = TypeAdapter(BrandName)
_CAPTION: TypeAdapter[str] = TypeAdapter(Caption)
EMBED_TIMEOUT_S = 5  # the range is a help: never long to wait for
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


async def _comparables(
    sessionmaker: Session, embedder: Embedder, kept: AssistOut, leaf: Row[Any], condition: str
) -> list[int]:
    async with sessionmaker() as db:
        text = await compose_text(
            db,
            texts=[kept.title or ""],
            category_id=leaf.id,
            attributes=kept.attributes,
            brand=kept.brand,
        )
    async with asyncio.timeout(EMBED_TIMEOUT_S):  # outside any transaction
        vector = checked_vector(await embedder.embed(text))
    async with sessionmaker() as db:
        return await repository.comparable_prices(
            db,
            category_id=leaf.id,
            condition=condition,
            vector=vector,
            model=embedder.model,
            limit=COMPARABLES,
        )


async def _price_range(
    sessionmaker: Session, embedder: Embedder | None, kept: AssistOut, leaf: Row[Any] | None
) -> PriceRange | None:
    """Q44: from the 20 listings online nearest to the suggestion, of its leaf and condition;
    none without an embedder, a title, a leaf or a condition. The range is a help: when the
    embedder or the database fails, the suggestion is still shown, without it."""
    if embedder is None or leaf is None or kept.title is None or kept.condition is None:
        return None
    try:
        prices = await _comparables(sessionmaker, embedder, kept, leaf, kept.condition)
    except Exception:
        logger.exception("catalog.assist_price_range_failed", suggestion_id=str(kept.suggestion_id))
        return None
    found = price_range(prices)
    if found is None:
        return None
    low, high = found
    return PriceRange(low=Money(amount_minor=low), high=Money(amount_minor=high))


async def assist(
    sessionmaker: Session,
    provider: ai.AIProvider,
    embedder: Embedder | None,
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
        kept = await _kept(db, call_id, suggestion, leaves, clock)
    leaf = leaves.get(kept.category.key) if kept.category else None
    found = await _price_range(sessionmaker, embedder, kept, leaf)
    shown = kept.model_copy(update={"price_range": found})
    await ai.record_shown(sessionmaker, call_id, shown.model_dump(mode="json"))
    return shown


def _kept_as_shown(shown: dict[str, Any], body: ListingDraftIn) -> list[str]:
    """The fields of the draft equal to what was shown (none for a field not suggested)."""
    category: dict[str, Any] = shown.get("category") or {}
    candidates: dict[str, tuple[Any, Any]] = {
        "title": (shown.get("title"), body.title),
        "category": (category.get("key"), body.category),
        "brand": (shown.get("brand"), body.brand),
        "condition": (shown.get("condition"), body.condition.value),
    }
    kept = [name for name, (was, now) in candidates.items() if was is not None and was == now]
    attributes: dict[str, Any] = shown.get("attributes") or {}
    return kept + [f"attributes.{k}" for k, v in attributes.items() if body.attributes.get(k) == v]


async def draft_from_suggestion(db: AsyncSession, *, seller_id: UUID, body: ListingDraftIn) -> None:
    """A draft created from a suggestion: the fields kept as shown are recorded (section 7.5),
    the caption goes with the main photo if it was among the photos shown to the AI. A
    suggestion not the seller's, that went wrong or that already served a draft is ignored: the
    draft never fails for it."""
    found = None
    if body.suggestion_id is not None:
        found = await ai.suggestion_for_draft(db, call_id=body.suggestion_id, user_id=seller_id)
    if body.suggestion_id is None or found is None:
        return
    shown, media_ids = found
    await ai.record_accepted(db, body.suggestion_id, _kept_as_shown(shown, body))
    caption = shown.get("caption")
    if caption and body.media_ids[0] in media_ids:
        await listing_photos.set_caption(db, body.media_ids[0], caption)
