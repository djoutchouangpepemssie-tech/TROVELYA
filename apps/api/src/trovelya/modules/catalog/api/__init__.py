"""HTTP routes of the catalog module (section 11.5, « Catalogue »)."""

from fastapi import APIRouter

from trovelya.modules.catalog.api import (
    categories,
    favorites,
    listings,
    my_listings,
    prices,
    staff,
)

router = APIRouter()
router.include_router(categories.router)
router.include_router(listings.router)
router.include_router(favorites.router)
router.include_router(prices.router)
router.include_router(my_listings.router)
router.include_router(staff.router)
