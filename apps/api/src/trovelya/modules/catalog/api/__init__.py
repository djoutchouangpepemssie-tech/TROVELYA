"""HTTP routes of the catalog module (section 11.5, « Catalogue »)."""

from fastapi import APIRouter

from trovelya.modules.catalog.api import categories

router = APIRouter()
router.include_router(categories.router)
