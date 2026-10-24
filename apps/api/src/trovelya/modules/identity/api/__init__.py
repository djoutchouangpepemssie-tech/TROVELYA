"""HTTP routes of the identity module (section 11.5, « Authentification et compte »)."""

from fastapi import APIRouter

from trovelya.modules.identity.api import auth, geo, me, oauth, passkeys, places, step_up, users

router = APIRouter()
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(oauth.router)
router.include_router(passkeys.auth_router)
router.include_router(passkeys.me_router)
router.include_router(step_up.router)
router.include_router(users.router)
router.include_router(geo.router)
router.include_router(places.router)
