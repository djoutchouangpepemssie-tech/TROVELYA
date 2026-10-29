"""The account's own profile: `GET /v1/me`, profile completion (Q11) and the age rule (E14).

Age rule B, decided by Arcel: only the birth year is known, so the age retained is
`current year - birth year - 1` (the birthday is assumed not to have passed yet). Sign-up from
`auth.min_signup_age` (15), adult from `auth.min_trade_age` (18). Under the minimum, nothing is
kept: the not-yet-completed account is erased and its sessions with it.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.core.errors import AppError, ErrorCode
from trovelya.core.flags import FlagService
from trovelya.modules.identity import repository
from trovelya.modules.identity.service.gdpr import erasure_grace_days
from trovelya.modules.identity.service.sessions import CurrentUser
from trovelya.modules.media.service import avatars as media_avatars
from trovelya.shared.clock import Clock

PARIS = ZoneInfo("Europe/Paris")
MIN_SIGNUP_AGE = 15
DEFAULT_MIN_TRADE_AGE = 18
# Feature flags the client needs to show or hide entry points.
CLIENT_FLAGS = ("auth.passkeys", "auth.oauth_google", "auth.oauth_apple", "media.uploads")
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


async def may_trade(db: AsyncSession, user_id: UUID, *, clock: Clock) -> bool:
    """Plan P2 Q1: a completed profile, adult by rule E14, an account neither suspended nor
    banned, and no erasure in progress."""
    facts = await repository.trade_facts(db, user_id)
    if facts is None or not facts.completed or facts.erasing:
        return False
    if facts.status not in ("active", "restricted"):
        return False
    return await is_minor(db, facts.birth_year, clock=clock) is False


async def me(
    db: AsyncSession,
    *,
    user: CurrentUser,
    flags: FlagService,
    clock: Clock,
    media_public_url: str | None,
) -> dict[str, Any]:
    row = await repository.me(db, user.id)
    avatar = await media_avatars.avatar_variants(
        db, row.avatar_media_id, public_url=media_public_url
    )
    erase_at = (
        row.erasure_requested_at + timedelta(days=await erasure_grace_days(db))
        if row.erasure_requested_at
        else None
    )
    return {
        "id": row.id,
        "email": row.email,
        "username": row.username,
        "display_name": row.display_name,
        "bio": row.bio,
        "avatar": avatar,
        # Only while the avatar can be shown: a photo withdrawn meanwhile is no avatar.
        "avatar_media_id": row.avatar_media_id if avatar is not None else None,
        "locale": row.locale,
        "country_code": row.country_code,
        "profile_completed": row.profile_completed,
        "roles": list(row.roles),
        "flags": {key: await flags.is_enabled(key, user_id=user.id) for key in CLIENT_FLAGS},
        "is_minor": await is_minor(db, row.birth_year, clock=clock),
        "erasure_requested_at": row.erasure_requested_at,
        "erase_at": erase_at,
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


async def update_profile(
    db: AsyncSession,
    *,
    user: CurrentUser,
    if_match: str | None,
    changes: dict[str, Any],
    clock: Clock,
) -> None:
    """`If-Match: <version>` is mandatory (428 without it, 412 when stale, section 11.1). A new
    avatar must be the member's own processed avatar photo; the one it replaces (or that is
    removed) is deleted."""
    if if_match is None:
        raise AppError(ErrorCode.PRECONDITION_REQUIRED, 428)
    try:
        version = int(if_match.strip().strip('"').removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise AppError(ErrorCode.PRECONDITION_FAILED, 412) from exc
    if not changes:
        current = await repository.me(db, user.id)
        if current.version != version:
            raise AppError(ErrorCode.PRECONDITION_FAILED, 412)
        return
    previous_avatar = None
    if "avatar_media_id" in changes:
        if changes["avatar_media_id"] is not None:
            await media_avatars.check_avatar(
                db, owner_id=user.id, media_id=changes["avatar_media_id"]
            )
        previous_avatar = (await repository.me(db, user.id)).avatar_media_id
    try:
        async with db.begin_nested():
            updated = await repository.update_profile(
                db, user_id=user.id, version=version, changes=changes
            )
    except IntegrityError as exc:
        raise AppError(ErrorCode.USERNAME_TAKEN, 409) from exc
    if not updated:
        raise AppError(ErrorCode.PRECONDITION_FAILED, 412)
    if previous_avatar is not None and previous_avatar != changes["avatar_media_id"]:
        await media_avatars.discard(db, previous_avatar, now=clock.now())


async def public_profile(db: AsyncSession, username: str) -> Row[Any]:
    normalised = username.strip().lower()
    row = (
        await repository.public_profile(db, normalised)
        if re.fullmatch(r"[a-z0-9_.]{3,30}", normalised)
        else None
    )
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    return row


async def public_avatar(
    db: AsyncSession, media_id: UUID | None, *, media_public_url: str | None
) -> list[dict[str, Any]] | None:
    return await media_avatars.avatar_variants(db, media_id, public_url=media_public_url)


async def public_seller(
    db: AsyncSession, user_id: UUID, *, media_public_url: str | None, own: bool = False
) -> dict[str, Any] | None:
    """What a listing shows of its seller; None when the seller is not to be shown (erasure
    requested, suspended, banned, deleted, profile not completed): their listings are hidden.
    `own`: the sellers reads their own listing, shown whatever their state."""
    row = await repository.public_seller(db, user_id, hidden_too=own)
    if row is None:
        return None
    return {
        "id": row.id,
        "username": row.username,
        "display_name": row.display_name,
        "member_since": row.member_since,
        "avatar": await public_avatar(db, row.avatar_media_id, media_public_url=media_public_url),
    }


async def default_zone_center(db: AsyncSession, user_id: UUID) -> tuple[float, float] | None:
    """The centre of the member's default search zone, from which distances are shown (Q17)."""
    row = await repository.default_zone_center(db, user_id)
    return (row.lat, row.lon) if row else None
