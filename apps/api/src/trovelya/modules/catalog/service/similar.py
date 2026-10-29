"""Similar listings (P2-T11b, ADR-0020, section 11.5). Never commits.

The nearest listings online by cosine distance between embeddings of the current model (two
coexist while reindexing), in the same universe (the first level of the category's path); never
the seller's own, nor those of a seller the visitor blocked or no longer shown. Without an
embedder, or a listing not yet embedded: none."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.catalog import repository
from trovelya.modules.catalog.schemas import SimilarListing
from trovelya.modules.media.service import listing_photos

SIMILAR_LIMIT = 8


async def similar_listings(
    db: AsyncSession,
    *,
    listing_id: UUID,
    viewer_id: UUID | None,
    model: str | None,
    media_public_url: str | None,
    limit: int = SIMILAR_LIMIT,
) -> list[SimilarListing]:
    target = None if model is None else await repository.similar_target(db, listing_id, model)
    if model is None or target is None:
        return []
    rows = await repository.similar_listings(
        db,
        listing_id=listing_id,
        seller_id=target.seller_id,
        universe=target.universe,
        model=model,
        viewer_id=viewer_id,
        limit=limit,
    )
    photos = await listing_photos.photo_variants_by_id(
        db, [m for row in rows for m in row["media_ids"]], public_url=media_public_url
    )
    found: list[dict[str, Any]] = [
        row
        | {
            "price": {"amount_minor": row["price_minor"], "currency": row["currency"]},
            "cover": next((photos[m] for m in row["media_ids"] if m in photos), None),
        }
        for row in rows
    ]
    return [SimilarListing.model_validate(row) for row in found]
