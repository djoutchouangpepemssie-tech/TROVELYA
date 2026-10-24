"""The account's own profile: `GET /v1/me`, profile completion (Q11) and the age rule (E14).

Age rule B, decided by Arcel: only the birth year is known, so the age retained is
`current year - birth year - 1` (the birthday is assumed not to have passed yet). Sign-up from
`auth.min_signup_age` (15), adult from `auth.min_trade_age` (18). Under the minimum, nothing is
kept: the not-yet-completed account is erased and its sessions with it.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.core.flags import FlagService
from trovelya.modules.identity import repository
from trovelya.modules.identity.service.sessions import CurrentUser
from trovelya.shared.clock import Clock

PARIS = ZoneInfo("Europe/Paris")
MIN_SIGNUP_AGE = 15
DEFAULT_MIN_TRADE_AGE = 18
# Feature flags the client needs to show or hide entry points.
CLIENT_FLAGS = ("auth.passkeys", "auth.oauth_google", "auth.oauth_apple")
_USERNAME_MAX = 30
_SUFFIX_TRIES = 50


def current_year(clock: Clock) -> int:
    return clock.now().astimezone(PARIS).year


def age_in(year: int, birth_year: int) -> int:
    """Rule B (E14): the birthday of the current year is assumed not to have passed."""
    return year - birth_year - 1


async def is_minor(db: AsyncSession, birth_year: int | None, *, clock: Clock) -> bool | None:
    if birth_year is None:
        return None
    adult = await repository.setting_int(db, "auth.min_trade_age", default=DEFAULT_MIN_TRADE_AGE)
    return age_in(current_year(clock), birth_year) < adult


async def me(
    db: AsyncSession, *, user: CurrentUser, flags: FlagService, clock: Clock
) -> dict[str, Any]:
    row = await repository.me(db, user.id)
    return {
        "id": row.id,
        "email": row.email,
        "username": row.username,
        "display_name": row.display_name,
        "bio": row.bio,
        "locale": row.locale,
        "country_code": row.country_code,
        "profile_completed": row.profile_completed,
        "roles": list(row.roles),
        "flags": {key: await flags.is_enabled(key, user_id=user.id) for key in CLIENT_FLAGS},
        "is_minor": await is_minor(db, row.birth_year, clock=clock),
        "erasure_requested_at": row.erasure_requested_at,
        "counters": {"unread_messages": 0, "notifications": 0},  # P3 and P6
        "version": row.version,
    }


def _username_base(email: str) -> str:
    local = email.split("@", 1)[0]
    ascii_only = unicodedata.normalize("NFKD", local).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9_.]", "_", ascii_only.lower()).strip("._")[:_USERNAME_MAX]
    return base if len(base) >= 3 else (base + "_membre")[:_USERNAME_MAX]


async def suggest_username(db: AsyncSession, *, user: CurrentUser) -> str:
    """A free username from the e-mail's local part, with a numeric suffix when taken."""
    base = _username_base(await repository.user_email(db, user.id))
    candidates = [base] + [
        f"{base[: _USERNAME_MAX - len(str(n))]}{n}" for n in range(1, _SUFFIX_TRIES)
    ]
    taken = await repository.taken_usernames(db, candidates)
    return next((c for c in candidates if c not in taken), f"membre_{user.id.hex[-8:]}")


@dataclass(frozen=True, slots=True)
class Completion:
    accepted: bool  # False: under the minimum age, the account has been erased


async def complete_profile(
    db: AsyncSession,
    *,
    user: CurrentUser,
    username: str,
    display_name: str,
    birth_year: int,
    terms_version: str,
    clock: Clock,
) -> Completion:
    now = clock.now()
    if birth_year > current_year(clock):
        raise AppError(ErrorCode.VALIDATION_ERROR, 422)
    if user.profile_completed:
        raise AppError(ErrorCode.PROFILE_ALREADY_COMPLETED, 409)
    minimum = await repository.setting_int(db, "auth.min_signup_age", default=MIN_SIGNUP_AGE)
    if age_in(current_year(clock), birth_year) < minimum:
        # Nothing is kept, not even the birth year (8.18); the caller commits and answers.
        await repository.erase_incomplete_account(db, user.id)
        return Completion(accepted=False)
    try:
        async with db.begin_nested():
            completed = await repository.complete_profile(
                db,
                user_id=user.id,
                username=username,
                display_name=display_name,
                birth_year=birth_year,
                now=now,
            )
    except IntegrityError as exc:
        raise AppError(ErrorCode.USERNAME_TAKEN, 409) from exc
    if not completed:
        raise AppError(ErrorCode.PROFILE_ALREADY_COMPLETED, 409)
    await repository.insert_consent(
        db,
        user_id=user.id,
        purpose="terms",
        granted=True,
        policy_version=terms_version,
        source="signup",
        now=now,
    )
    return Completion(accepted=True)
