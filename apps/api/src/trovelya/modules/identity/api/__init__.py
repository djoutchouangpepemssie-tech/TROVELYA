"""HTTP routes of the identity module (section 11.5, « Authentification et compte »)."""

from fastapi import APIRouter

from trovelya.modules.identity.api import auth, me, oauth, passkeys, step_up

router = APIRouter()
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(oauth.router)
router.include_router(passkeys.auth_router)
router.include_router(passkeys.me_router)
router.include_router(step_up.router)
