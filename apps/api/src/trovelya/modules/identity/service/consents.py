"""Consent records (RGPD art. 7, section 13.3): one row per choice, the latest one wins.

Anonymous visitors are recognised by `__Host-trv_anon`, a random identifier kept 13 months
(CNIL), created only when they make a choice. Their choices are attached to the account when
they sign in on the same browser.
"""

import re
import secrets
from datetime import timedelta
from typing import Any, get_args
from uuid import UUID

from fastapi import Response
from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.identity import repository
from trovelya.modules.identity.schemas import ConsentPurpose
from trovelya.shared.clock import Clock

ANON_COOKIE = "__Host-trv_anon"
ANON_COOKIE_MAX_AGE = timedelta(days=395)  # 13 months
ACTIVE_PURPOSES_SETTING = "consent.active_purposes"
PURPOSES: tuple[ConsentPurpose, ...] = get_args(ConsentPurpose)
SOURCE = "web"
_ANON_PATTERN = re.compile(r"[A-Za-z0-9_-]{22,64}")


def valid_anonymous_id(value: str | None) -> str | None:
    """The cookie's value when it looks like one we issued, else None (a new one is issued)."""
    return value if value is not None and _ANON_PATTERN.fullmatch(value) else None


def new_anonymous_id() -> str:
    return secrets.token_urlsafe(24)


def set_anonymous_cookie(response: Response, anonymous_id: str) -> None:
    response.set_cookie(
        ANON_COOKIE,
        anonymous_id,
        max_age=int(ANON_COOKIE_MAX_AGE.total_seconds()),
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


async def active_purposes(db: AsyncSession) -> list[ConsentPurpose]:
    """Q15: non-essential purposes in use (platform setting, none in P1)."""
    value: Any = await repository.setting_json(db, ACTIVE_PURPOSES_SETTING)
    if not isinstance(value, list):
        return []
    return [p for p in PURPOSES if p in value]


async def latest(
    db: AsyncSession, *, user_id: UUID | None, anonymous_id: str | None
) -> list[Row[Any]]:
    if user_id is None and anonymous_id is None:
        return []
    return await repository.latest_consents(db, user_id=user_id, anonymous_id=anonymous_id)


async def record(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    anonymous_id: str | None,
    purpose: str,
    granted: bool,
    policy_version: str,
    clock: Clock,
) -> None:
    await repository.insert_consent(
        db,
        user_id=user_id,
        anonymous_id=None if user_id is not None else anonymous_id,
        purpose=purpose,
        granted=granted,
        policy_version=policy_version,
        source=SOURCE,
        now=clock.now(),
    )


async def attach_on_sign_in(db: AsyncSession, *, cookie: str | None, user_id: UUID) -> None:
    """Choices made on this browser before signing in now belong to the account."""
    anonymous_id = valid_anonymous_id(cookie)
    if anonymous_id is not None:
        await repository.attach_anonymous_consents(db, anonymous_id=anonymous_id, user_id=user_id)
