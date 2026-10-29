"""Price history of a listing online (P2-T08b, section 11.5, plan Q43)."""

from uuid import UUID

from fastapi import APIRouter

from trovelya.core.db import Uow
from trovelya.modules.catalog.schemas import PriceHistory
from trovelya.modules.catalog.service import prices

router = APIRouter(prefix="/v1/listings", tags=["catalog"])


@router.get(
    "/{listing_id}/price-history",
    operation_id="listing_price_history",
    responses={404: {"description": "No such listing online"}},
)
async def price_history(listing_id: UUID, db: Uow) -> PriceHistory:
    """The prices shown online since the first time online, oldest first; anybody may read."""
    currency, points = await prices.price_history(db, listing_id)
    return PriceHistory.model_validate(
        {
            "prices": [
                {"at": at, "price": {"amount_minor": price, "currency": currency}}
                for at, price in points
            ]
        }
    )
