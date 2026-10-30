"""A draft created after the AI help (P2-T06a3b, plan Q47). Never commits.

The seller sends back the caption they keep (W09 shows the AI's, to keep, correct or empty):
it goes with the main photo, screened at publication like the title, and joins the listing's
embedding. With `suggestion_id`, the fields kept as shown are recorded (`accepted_fields`,
section 7.5), compared with the values stored. A suggestion serves one draft, of its member,
and only if it went well; otherwise it is ignored: the draft never fails for it."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.ai import service as ai
from trovelya.modules.catalog.schemas import ListingDraftIn
from trovelya.modules.catalog.service.draft_rules import brand_slug
from trovelya.modules.media.service import listing_photos


def kept_as_shown(
    shown: dict[str, Any], body: ListingDraftIn, attributes: dict[str, Any]
) -> list[str]:
    """The fields of the draft equal to what was shown (none for a field not suggested);
    `attributes` as stored, the brand by its slug (the stored brand is found by it)."""
    category: dict[str, Any] = shown.get("category") or {}
    brand = shown.get("brand")
    candidates: dict[str, tuple[Any, Any]] = {
        "title": (shown.get("title"), body.title),
        "category": (category.get("key"), body.category),
        "brand": (brand and brand_slug(brand), body.brand and brand_slug(body.brand)),
        "condition": (shown.get("condition"), body.condition.value),
        "caption": (shown.get("caption"), body.caption),
    }
    kept = [name for name, (was, now) in candidates.items() if was is not None and was == now]
    suggested: dict[str, Any] = shown.get("attributes") or {}
    return kept + [f"attributes.{k}" for k, v in suggested.items() if attributes.get(k) == v]


async def record_choices(
    db: AsyncSession, *, seller_id: UUID, body: ListingDraftIn, attributes: dict[str, Any]
) -> None:
    if body.caption is not None:
        await listing_photos.set_caption(db, body.media_ids[0], body.caption)
    if body.suggestion_id is None:
        return
    found = await ai.suggestion_for_draft(db, call_id=body.suggestion_id, user_id=seller_id)
    if found is not None:
        shown, _ = found
        fields = kept_as_shown(shown, body, attributes)
        await ai.record_accepted(db, body.suggestion_id, fields)
