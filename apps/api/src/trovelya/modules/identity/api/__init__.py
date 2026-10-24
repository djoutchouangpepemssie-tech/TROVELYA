"""HTTP routes of the identity module (section 11.5, « Authentification et compte »)."""

from fastapi import APIRouter

from trovelya.modules.identity.api import auth, me

router = APIRouter()
router.include_router(auth.router)
router.include_router(me.router)
