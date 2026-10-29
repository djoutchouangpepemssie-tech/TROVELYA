"""The listing page (`GET /v1/listings/{id}`, P2-T03b3a, section 11.5).

An active listing is read by anybody, any other only by its seller: 404 for everyone else, as
if it did not exist. A seller who is not to be shown (erasure requested, Q13; suspended,
banned) has no listing to read for others. Never a coordinate (8.11): the place name and, for a
signed-in visitor with a default zone, the distance to the public position, rounded (Q17, E13).
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.core.pagination import decode_cursor, encode_cursor
from trovelya.modules.catalog import repository
from trovelya.modules.catalog.schemas import ListingPage, ListingSummary, ListingSummaryPage
from trovelya.modules.catalog.service.categories import LOCALE
from trovelya.modules.catalog.service.positions import round_distance
from trovelya.modules.identity.service import default_zone_center, public_seller
from trovelya.modules.media.service import listing_photos

NIL_ID = UUID(int=0)


def _not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, 404)


async def _attributes_shown(
    db: AsyncSession, category_id: UUID, values: dict[str, Any]
) -> list[dict[str, Any]]:
    """The listing's attributes in the category's order, with their labels."""
    order = [row.key for row in await repository.attribute_rules(db, category_id)]
    definitions = {row.key: row for row in await repository.attributes(db, list(values))}
    shown: list[dict[str, Any]] = []
    for key in sorted(values, key=lambda k: order.index(k) if k in order else len(order)):
        definition = definitions.get(key)
        if definition is None:  # an attribute retired from the seed since: not shown
            continue
        value = values[key]
        enum_values: list[dict[str, Any]] = definition.enum_values or []
        labels: dict[str, str] = {v["key"]: v["names"][LOCALE] for v in enum_values}
        shown.append(
            {
                "key": key,
                "name": definition.names[LOCALE],
                "value": value,
                "value_name": labels.get(value) if isinstance(value, str) else None,
                "unit": definition.unit,
            }
        )
    return shown


async def listing_page(
    db: AsyncSession,
    *,
    listing_id: UUID,
    viewer_id: UUID | None,
    media_public_url: str | None,
) -> ListingPage:
    viewer = await default_zone_center(db, viewer_id) if viewer_id else None
    row = await repository.listing_page(db, listing_id, viewer)
    own = row is not None and viewer_id == row["seller_id"]
    visible = row is not None and (own or row["status"] == "active")
    # The seller is read whatever happens (a nil id when the listing is not to be shown): every
    # 404 costs the same queries, so its time says nothing of why (unknown, someone else's draft,
    # seller in erasure grace or sanctioned).
    seller = await public_seller(
        db,
        row["seller_id"] if row and visible else NIL_ID,
        media_public_url=media_public_url,
        own=own,
    )
    if row is None or not visible or seller is None:
        raise _not_found()
    return ListingPage.model_validate(
        {
            **row,
            "category": {"key": row["category_key"], "name": row["category_name"]},
            "attributes": await _attributes_shown(db, row["category_id"], row["attributes"]),
            "price": {"amount_minor": row["price_minor"], "currency": row["currency"]},
            "distance": None if row["distance_m"] is None else round_distance(row["distance_m"]),
            "photos": await listing_photos.photo_variants(
                db, row["media_ids"], public_url=media_public_url
            ),
            "seller": seller,
        }
    )


async def seller_listings(
    db: AsyncSession,
    *,
    seller_id: UUID,
    status: str | None,
    cursor: str | None,
    limit: int,
    media_public_url: str | None,
) -> ListingSummaryPage:
    """The seller's listings, newest first, any status but deleted ones (W10)."""
    rows = await repository.seller_listings(
        db, seller_id=seller_id, status=status, after=decode_cursor(cursor), limit=limit + 1
    )
    page, has_more = rows[:limit], len(rows) > limit
    shown = await listing_photos.photo_variants_by_id(
        db, [media_id for row in page for media_id in row["media_ids"]], public_url=media_public_url
    )
    return ListingSummaryPage(
        data=[
            ListingSummary.model_validate(
                row
                | {
                    "price": {"amount_minor": row["price_minor"], "currency": row["currency"]},
                    # The first photo still shown (one removed by moderation is skipped).
                    "cover": next((shown[m] for m in row["media_ids"] if m in shown), None),
                }
            )
            for row in page
        ],
        next_cursor=encode_cursor(page[-1]["created_at"], page[-1]["id"]) if has_more else None,
        has_more=has_more,
    )
