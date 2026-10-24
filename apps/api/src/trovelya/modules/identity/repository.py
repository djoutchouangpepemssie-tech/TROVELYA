"""SQL of the identity module. Only this module's service reads or writes these tables."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Row, TextClause, bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.identity.models import BLOCKED_STATUSES, SessionKind
from trovelya.shared.ids import new_id

_BLOCKED = [status.value for status in BLOCKED_STATUSES]

_INSERT_SESSION = text(
    "INSERT INTO sessions (id, user_id, token_hash, kind, created_at, last_used_at, expires_at,"
    " ip, user_agent, device_label, country_code, mfa_at)"
    " VALUES (:id, :user_id, :token_hash, :kind, :now, :now, :expires_at, CAST(:ip AS inet),"
    " :user_agent, :device_label, :country, :mfa_at)"
)

_FIND_ACTIVE = text(
    "SELECT s.id, s.user_id, s.kind, s.mfa_at, s.last_used_at, s.expires_at,"
    " u.is_staff, u.profile_completed_at IS NOT NULL AS profile_completed"
    " FROM sessions s JOIN users u ON u.id = s.user_id"
    " WHERE s.token_hash = :token_hash AND s.revoked_at IS NULL"
    " AND s.expires_at > :now AND s.last_used_at > :idle_cutoff"
    " AND u.status::text <> ALL(:blocked)"
)

_TOUCH = text("UPDATE sessions SET last_used_at = :now WHERE id = :id")

_REVOKE_ONE = text(
    "UPDATE sessions SET revoked_at = :now"
    " WHERE id = :id AND user_id = :user_id AND revoked_at IS NULL RETURNING id"
)

_REVOKE_ALL = text(
    "UPDATE sessions SET revoked_at = :now"
    " WHERE user_id = :user_id AND revoked_at IS NULL"
    " AND (CAST(:except_id AS uuid) IS NULL OR id <> :except_id)"
)

_LIST_ACTIVE = text(
    "SELECT id, created_at, last_used_at, device_label, country_code FROM sessions"
    " WHERE user_id = :user_id AND revoked_at IS NULL"
    " AND expires_at > :now AND last_used_at > :idle_cutoff"
    " ORDER BY last_used_at DESC"
)


async def insert_session(
    db: AsyncSession,
    *,
    session_id: UUID,
    user_id: UUID,
    token_hash: bytes,
    kind: SessionKind,
    now: datetime,
    expires_at: datetime,
    ip: str | None,
    user_agent: str | None,
    device_label: str | None,
    country: str | None,
    mfa_at: datetime | None,
) -> None:
    await db.execute(
        _INSERT_SESSION,
        {
            "id": session_id,
            "user_id": user_id,
            "token_hash": token_hash,
            "kind": kind,
            "now": now,
            "expires_at": expires_at,
            "ip": ip,
            "user_agent": user_agent,
            "device_label": device_label,
            "country": country,
            "mfa_at": mfa_at,
        },
    )


async def find_active_session(
    db: AsyncSession, token_hash: bytes, *, now: datetime, idle_cutoff: datetime
) -> Row[Any] | None:
    result = await db.execute(
        _FIND_ACTIVE,
        {"token_hash": token_hash, "now": now, "idle_cutoff": idle_cutoff, "blocked": _BLOCKED},
    )
    return result.one_or_none()


async def touch_session(db: AsyncSession, session_id: UUID, *, now: datetime) -> None:
    await db.execute(_TOUCH, {"id": session_id, "now": now})


async def revoke_session(
    db: AsyncSession, *, session_id: UUID, user_id: UUID, now: datetime
) -> bool:
    result = await db.execute(_REVOKE_ONE, {"id": session_id, "user_id": user_id, "now": now})
    return result.one_or_none() is not None


async def revoke_sessions(
    db: AsyncSession, *, user_id: UUID, except_id: UUID | None, now: datetime
) -> None:
    await db.execute(_REVOKE_ALL, {"user_id": user_id, "except_id": except_id, "now": now})


async def list_active_sessions(
    db: AsyncSession, *, user_id: UUID, now: datetime, idle_cutoff: datetime
) -> list[Row[Any]]:
    result = await db.execute(
        _LIST_ACTIVE, {"user_id": user_id, "now": now, "idle_cutoff": idle_cutoff}
    )
    return list(result.all())


# --- Magic links and sign-up -----------------------------------------------------------------

_SETTING_INT = text("SELECT value FROM platform_settings WHERE key = :key")

_INSERT_MAGIC_LINK = text(
    "INSERT INTO magic_links (id, email, token_hash, purpose, expires_at, ip, created_at)"
    " VALUES (:id, :email, :token_hash, :purpose, :expires_at, CAST(:ip AS inet), :now)"
)

# Atomic: two concurrent clicks on the same link, only one gets the row back.
_CONSUME_MAGIC_LINK = text(
    "UPDATE magic_links SET consumed_at = :now"
    " WHERE token_hash = :token_hash AND purpose = :purpose"
    " AND consumed_at IS NULL AND expires_at > :now RETURNING email"
)

_PURGE_MAGIC_LINKS = text("DELETE FROM magic_links WHERE expires_at < :cutoff")

# Both return the same columns: id, is_staff, status, profile_completed, email_verified.
_FIND_USER_BY_EMAIL = text(
    "SELECT u.id, u.is_staff, u.status::text AS status,"
    " u.profile_completed_at IS NOT NULL AS profile_completed,"
    " u.email_verified_at IS NOT NULL AS email_verified"
    " FROM users u WHERE u.email = :email"
)

_FIND_USER_BY_IDENTITY = text(
    "SELECT u.id, u.is_staff, u.status::text AS status,"
    " u.profile_completed_at IS NOT NULL AS profile_completed,"
    " u.email_verified_at IS NOT NULL AS email_verified"
    " FROM auth_identities i JOIN users u ON u.id = i.user_id"
    " WHERE i.provider = :provider AND i.provider_subject = :subject"
)

_INSERT_IDENTITY = text(
    "INSERT INTO auth_identities (id, user_id, provider, provider_subject, created_at)"
    " VALUES (:id, :user_id, :provider, :subject, :now)"
    " ON CONFLICT (provider, provider_subject) DO NOTHING"
)

_CREATE_USER = text(
    "INSERT INTO users (id, email, username, display_name, email_verified_at, created_at)"
    " VALUES (:id, :email, :username, :display_name, :now, :now)"
    " ON CONFLICT (email) DO NOTHING RETURNING id"
)

_CREATE_PREFERENCES = text(
    "INSERT INTO user_preferences (user_id) VALUES (:user_id) ON CONFLICT DO NOTHING"
)

_MARK_EMAIL_VERIFIED = text(
    "UPDATE users SET email_verified_at = coalesce(email_verified_at, :now) WHERE id = :id"
)


async def setting_json(db: AsyncSession, key: str) -> Any:
    """The JSON value of a platform setting, None when it is not set."""
    return await db.scalar(_SETTING_INT, {"key": key})


async def setting_int(db: AsyncSession, key: str, *, default: int) -> int:
    value = await db.scalar(_SETTING_INT, {"key": key})
    return int(value) if value is not None else default


async def insert_magic_link(
    db: AsyncSession,
    *,
    link_id: UUID,
    email: str,
    token_hash: bytes,
    purpose: str,
    expires_at: datetime,
    ip: str | None,
    now: datetime,
) -> None:
    await db.execute(
        _INSERT_MAGIC_LINK,
        {
            "id": link_id,
            "email": email,
            "token_hash": token_hash,
            "purpose": purpose,
            "expires_at": expires_at,
            "ip": ip,
            "now": now,
        },
    )


async def consume_magic_link(
    db: AsyncSession, *, token_hash: bytes, purpose: str, now: datetime
) -> str | None:
    result = await db.execute(
        _CONSUME_MAGIC_LINK, {"token_hash": token_hash, "purpose": purpose, "now": now}
    )
    return result.scalar_one_or_none()


async def purge_magic_links(db: AsyncSession, *, cutoff: datetime) -> int:
    result = await db.execute(_PURGE_MAGIC_LINKS, {"cutoff": cutoff})
    return result.rowcount  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]


async def find_user_by_email(db: AsyncSession, email: str) -> Row[Any] | None:
    return (await db.execute(_FIND_USER_BY_EMAIL, {"email": email})).one_or_none()


async def find_user_by_identity(db: AsyncSession, provider: str, subject: str) -> Row[Any] | None:
    params = {"provider": provider, "subject": subject}
    return (await db.execute(_FIND_USER_BY_IDENTITY, params)).one_or_none()


async def link_identity(
    db: AsyncSession,
    *,
    identity_id: UUID,
    user_id: UUID,
    provider: str,
    subject: str,
    now: datetime,
) -> None:
    await db.execute(
        _INSERT_IDENTITY,
        {
            "id": identity_id,
            "user_id": user_id,
            "provider": provider,
            "subject": subject,
            "now": now,
        },
    )


async def create_user(
    db: AsyncSession, *, user_id: UUID, email: str, username: str, display_name: str, now: datetime
) -> bool:
    """False when another request created the account for this e-mail at the same time."""
    result = await db.execute(
        _CREATE_USER,
        {
            "id": user_id,
            "email": email,
            "username": username,
            "display_name": display_name,
            "now": now,
        },
    )
    if result.scalar_one_or_none() is None:
        return False
    await db.execute(_CREATE_PREFERENCES, {"user_id": user_id})
    return True


async def mark_email_verified(db: AsyncSession, user_id: UUID, *, now: datetime) -> None:
    await db.execute(_MARK_EMAIL_VERIFIED, {"id": user_id, "now": now})


_NEW_SESSION = text(
    "SELECT s.created_at, s.device_label, s.country_code, u.email,"
    " EXISTS (SELECT 1 FROM sessions p WHERE p.user_id = s.user_id AND p.id <> s.id"
    "   AND p.created_at <= s.created_at) AS has_previous,"
    " EXISTS (SELECT 1 FROM sessions p WHERE p.user_id = s.user_id AND p.id <> s.id"
    "   AND p.created_at <= s.created_at"
    "   AND p.created_at > s.created_at - CAST(:window AS interval)"
    "   AND p.device_label IS NOT DISTINCT FROM s.device_label"
    "   AND p.country_code IS NOT DISTINCT FROM s.country_code) AS known_context"
    " FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = :id"
)


async def find_session_context(
    db: AsyncSession, session_id: UUID, *, window: timedelta
) -> Row[Any] | None:
    """A session with its owner's address and whether its device and country were seen."""
    result = await db.execute(_NEW_SESSION, {"id": session_id, "window": window})
    return result.one_or_none()


# --- Passkeys -------------------------------------------------------------------------------

_INSERT_PASSKEY = text(
    "INSERT INTO passkeys (id, user_id, credential_id, public_key, sign_count, transports, name,"
    " created_at) VALUES (:id, :user_id, :credential_id, :public_key, :sign_count, :transports,"
    " :name, :now) ON CONFLICT (credential_id) DO NOTHING"
    " RETURNING id, name, created_at, last_used_at"
)

_CREDENTIAL_IDS = text("SELECT credential_id FROM passkeys WHERE user_id = :user_id")

_FIND_PASSKEY = text(
    "SELECT p.id, p.user_id, p.public_key, p.sign_count, u.is_staff, u.status::text AS status,"
    " u.profile_completed_at IS NOT NULL AS profile_completed"
    " FROM passkeys p JOIN users u ON u.id = p.user_id WHERE p.credential_id = :credential_id"
)

# Two sign-ins racing with the same counter: only one moves it forward.
_USE_PASSKEY = text(
    "UPDATE passkeys SET sign_count = :new_count, last_used_at = :now"
    " WHERE id = :id AND sign_count = :old_count RETURNING id"
)

_LIST_PASSKEYS = text(
    "SELECT id, name, created_at, last_used_at FROM passkeys WHERE user_id = :user_id"
    " ORDER BY created_at"
)

_RENAME_PASSKEY = text(
    "UPDATE passkeys SET name = :name WHERE id = :id AND user_id = :user_id"
    " RETURNING id, name, created_at, last_used_at"
)

_DELETE_PASSKEY = text("DELETE FROM passkeys WHERE id = :id AND user_id = :user_id RETURNING id")


async def insert_passkey(
    db: AsyncSession,
    *,
    passkey_id: UUID,
    user_id: UUID,
    credential_id: bytes,
    public_key: bytes,
    sign_count: int,
    transports: list[str] | None,
    name: str,
    now: datetime,
) -> Row[Any] | None:
    """None when this credential is already registered."""
    result = await db.execute(
        _INSERT_PASSKEY,
        {
            "id": passkey_id,
            "user_id": user_id,
            "credential_id": credential_id,
            "public_key": public_key,
            "sign_count": sign_count,
            "transports": transports,
            "name": name,
            "now": now,
        },
    )
    return result.one_or_none()


async def user_email(db: AsyncSession, user_id: UUID) -> str:
    email: str = await db.scalar(text("SELECT email FROM users WHERE id = :id"), {"id": user_id})
    return email


async def credential_ids(db: AsyncSession, user_id: UUID) -> list[bytes]:
    return list((await db.scalars(_CREDENTIAL_IDS, {"user_id": user_id})).all())


async def find_passkey(db: AsyncSession, credential_id: bytes) -> Row[Any] | None:
    return (await db.execute(_FIND_PASSKEY, {"credential_id": credential_id})).one_or_none()


async def use_passkey(
    db: AsyncSession, passkey_id: UUID, *, old_count: int, new_count: int, now: datetime
) -> bool:
    params = {"id": passkey_id, "old_count": old_count, "new_count": new_count, "now": now}
    return (await db.execute(_USE_PASSKEY, params)).one_or_none() is not None


async def list_passkeys(db: AsyncSession, user_id: UUID) -> list[Row[Any]]:
    return list((await db.execute(_LIST_PASSKEYS, {"user_id": user_id})).all())


async def rename_passkey(
    db: AsyncSession, *, passkey_id: UUID, user_id: UUID, name: str
) -> Row[Any] | None:
    params = {"id": passkey_id, "user_id": user_id, "name": name}
    return (await db.execute(_RENAME_PASSKEY, params)).one_or_none()


async def delete_passkey(db: AsyncSession, *, passkey_id: UUID, user_id: UUID) -> bool:
    params = {"id": passkey_id, "user_id": user_id}
    return (await db.execute(_DELETE_PASSKEY, params)).one_or_none() is not None


# --- Profile --------------------------------------------------------------------------------

_ME = text(
    "SELECT u.id, u.email::text AS email, u.username::text AS username, u.display_name, u.bio,"
    " u.locale, u.country_code, u.birth_year, u.profile_completed_at IS NOT NULL"
    " AS profile_completed, u.erasure_requested_at, u.version,"
    " coalesce(array_agg(r.role_key ORDER BY r.role_key)"
    "   FILTER (WHERE r.role_key IS NOT NULL), '{}') AS roles"
    " FROM users u LEFT JOIN user_roles r ON r.user_id = u.id WHERE u.id = :id GROUP BY u.id"
)

_TAKEN_USERNAMES = text("SELECT username::text FROM users WHERE username = ANY(:candidates)")

_COMPLETE_PROFILE = text(
    "UPDATE users SET username = :username, display_name = :display_name,"
    " birth_year = :birth_year, profile_completed_at = :now"
    " WHERE id = :id AND profile_completed_at IS NULL RETURNING id"
)

_INSERT_CONSENT = text(
    "INSERT INTO consents"
    " (id, user_id, anonymous_id, purpose, granted, policy_version, source, created_at)"
    " VALUES (:id, :user_id, :anonymous_id, :purpose, :granted, :policy_version, :source, :now)"
)

# Latest choice per purpose of a member, or of an anonymous browser (`terms` is not a cookie
# choice and stays out). Ties on the timestamp are broken by the time-ordered id.
_LATEST_CONSENTS = text(
    "SELECT DISTINCT ON (purpose) purpose, granted, policy_version, created_at FROM consents"
    " WHERE purpose <> 'terms'"
    " AND (user_id = :user_id OR (CAST(:user_id AS uuid) IS NULL AND anonymous_id = :anonymous_id"
    " AND user_id IS NULL))"
    " ORDER BY purpose, created_at DESC, id DESC"
)

_ATTACH_ANONYMOUS_CONSENTS = text(
    "UPDATE consents SET user_id = :user_id WHERE anonymous_id = :anonymous_id AND user_id IS NULL"
)

# Everything a not-yet-completed account can own (every other route needs a completed profile).
_ERASE_INCOMPLETE = (
    "DELETE FROM sessions WHERE user_id = :id",
    "DELETE FROM auth_identities WHERE user_id = :id",
    "DELETE FROM user_preferences WHERE user_id = :id",
    "DELETE FROM consents WHERE user_id = :id",
    "DELETE FROM magic_links WHERE email = (SELECT email FROM users WHERE id = :id)",
    "DELETE FROM users WHERE id = :id AND profile_completed_at IS NULL",
)


async def me(db: AsyncSession, user_id: UUID) -> Row[Any]:
    return (await db.execute(_ME, {"id": user_id})).one()


async def taken_usernames(db: AsyncSession, candidates: list[str]) -> set[str]:
    return set((await db.scalars(_TAKEN_USERNAMES, {"candidates": candidates})).all())


async def complete_profile(
    db: AsyncSession,
    *,
    user_id: UUID,
    username: str,
    display_name: str,
    birth_year: int,
    now: datetime,
) -> bool:
    """False when the profile was already completed. Raises IntegrityError if the username
    is taken (unique, case-insensitive)."""
    params = {
        "id": user_id,
        "username": username,
        "display_name": display_name,
        "birth_year": birth_year,
        "now": now,
    }
    return (await db.execute(_COMPLETE_PROFILE, params)).one_or_none() is not None


async def insert_consent(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    anonymous_id: str | None = None,
    purpose: str,
    granted: bool,
    policy_version: str,
    source: str,
    now: datetime,
) -> None:
    await db.execute(
        _INSERT_CONSENT,
        {
            "id": new_id(),
            "user_id": user_id,
            "anonymous_id": anonymous_id,
            "purpose": purpose,
            "granted": granted,
            "policy_version": policy_version,
            "source": source,
            "now": now,
        },
    )


async def latest_consents(
    db: AsyncSession, *, user_id: UUID | None, anonymous_id: str | None
) -> list[Row[Any]]:
    result = await db.execute(_LATEST_CONSENTS, {"user_id": user_id, "anonymous_id": anonymous_id})
    return list(result.all())


async def attach_anonymous_consents(db: AsyncSession, *, anonymous_id: str, user_id: UUID) -> None:
    await db.execute(_ATTACH_ANONYMOUS_CONSENTS, {"anonymous_id": anonymous_id, "user_id": user_id})


async def erase_incomplete_account(db: AsyncSession, user_id: UUID) -> None:
    for sql in _ERASE_INCOMPLETE:
        await db.execute(text(sql), {"id": user_id})


# One static statement: a field changes only when its `set_*` flag is true.
_UPDATE_PROFILE = text(
    "UPDATE users SET"
    " username = CASE WHEN :set_username THEN :username ELSE username END,"
    " display_name = CASE WHEN :set_display_name THEN :display_name ELSE display_name END,"
    " bio = CASE WHEN :set_bio THEN :bio ELSE bio END,"
    " locale = CASE WHEN :set_locale THEN :locale ELSE locale END"
    " WHERE id = :id AND version = :version RETURNING id"
)
_EDITABLE = ("username", "display_name", "bio", "locale")

_PUBLIC_PROFILE = text(
    "SELECT u.username::text AS username, u.display_name, u.bio,"
    " (u.created_at AT TIME ZONE 'Europe/Paris')::date AS member_since,"
    " (SELECT count(*) FROM follows f WHERE f.followee_user_id = u.id) AS followers_count,"
    " (SELECT count(*) FROM follows f WHERE f.follower_id = u.id) AS following_count"
    " FROM users u WHERE u.username = :username AND u.status IN ('active', 'restricted')"
    " AND u.erasure_requested_at IS NULL AND u.profile_completed_at IS NOT NULL"
)


async def update_profile(
    db: AsyncSession, *, user_id: UUID, version: int, changes: dict[str, str | None]
) -> bool:
    """False when `version` is not the current one (optimistic locking, 11.1). Raises
    IntegrityError if the new username is taken."""
    params: dict[str, Any] = {"id": user_id, "version": version}
    for field in _EDITABLE:
        params[f"set_{field}"] = field in changes
        params[field] = changes.get(field)
    return (await db.execute(_UPDATE_PROFILE, params)).one_or_none() is not None


async def public_profile(db: AsyncSession, username: str) -> Row[Any] | None:
    return (await db.execute(_PUBLIC_PROFILE, {"username": username})).one_or_none()


_EMAIL_IN_USE = text("SELECT EXISTS (SELECT 1 FROM users WHERE email = :email)")

_CHANGE_EMAIL = text(
    "UPDATE users SET email = :email, email_verified_at = :now"
    " WHERE id = :id AND status::text <> ALL(:blocked) RETURNING id"
)


async def email_in_use(db: AsyncSession, email: str) -> bool:
    return bool(await db.scalar(_EMAIL_IN_USE, {"email": email}))


async def change_email(db: AsyncSession, *, user_id: UUID, email: str, now: datetime) -> bool:
    """False for an unknown or blocked account. Raises IntegrityError if the address is taken."""
    params = {"id": user_id, "email": email, "now": now, "blocked": _BLOCKED}
    return (await db.execute(_CHANGE_EMAIL, params)).one_or_none() is not None


# --- Addresses and search zones -------------------------------------------------------------


_LIST_ADDRESSES = text(
    "SELECT"
    " id, label, full_name, line1, line2, postal_code, city, country_code, phone_e164,"
    " ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon,"
    " is_default_shipping, created_at"
    " FROM addresses WHERE user_id = :user_id AND deleted_at IS NULL ORDER BY created_at, id"
)

_COUNT_ADDRESSES = text(
    "SELECT count(*) FROM addresses WHERE user_id = :user_id AND deleted_at IS NULL"
)

_CLEAR_DEFAULT_ADDRESS = text(
    "UPDATE addresses SET is_default_shipping = false"
    " WHERE user_id = :user_id AND is_default_shipping"
)

_INSERT_ADDRESS = text(
    "INSERT INTO addresses (id, user_id, label, full_name, line1, line2, postal_code, city,"
    " country_code, phone_e164, location, is_default_shipping)"
    " VALUES (:id, :user_id, :label, :full_name, :line1, :line2, :postal_code, :city,"
    " :country_code, :phone_e164,"
    " CASE WHEN CAST(:lat AS double precision) IS NULL THEN NULL"
    " ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision),"
    " CAST(:lat AS double precision)), 4326)::geography END, :is_default_shipping)"
    " RETURNING"
    " id, label, full_name, line1, line2, postal_code, city, country_code, phone_e164,"
    " ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon,"
    " is_default_shipping, created_at"
)

# One static statement: a field changes only when its `set_*` flag is true.
_UPDATE_ADDRESS = text(
    "UPDATE addresses SET"
    " label = CASE WHEN :set_label THEN CAST(:label AS text) ELSE label END,"
    " full_name = CASE WHEN :set_full_name THEN CAST(:full_name AS text) ELSE full_name END,"
    " line1 = CASE WHEN :set_line1 THEN CAST(:line1 AS text) ELSE line1 END,"
    " line2 = CASE WHEN :set_line2 THEN CAST(:line2 AS text) ELSE line2 END,"
    " postal_code = CASE WHEN :set_postal_code THEN CAST(:postal_code AS text)"
    "   ELSE postal_code END,"
    " city = CASE WHEN :set_city THEN CAST(:city AS text) ELSE city END,"
    " country_code = CASE WHEN :set_country_code THEN CAST(:country_code AS char(2))"
    "   ELSE country_code END,"
    " phone_e164 = CASE WHEN :set_phone_e164 THEN CAST(:phone_e164 AS text)"
    "   ELSE phone_e164 END,"
    " location = CASE WHEN :set_location THEN"
    "   CASE WHEN CAST(:lat AS double precision) IS NULL THEN NULL"
    "   ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision),"
    "   CAST(:lat AS double precision)), 4326)::geography END ELSE location END,"
    " is_default_shipping = CASE WHEN :set_is_default_shipping"
    "   THEN CAST(:is_default_shipping AS boolean) ELSE is_default_shipping END"
    " WHERE id = :id AND user_id = :user_id AND deleted_at IS NULL"
    " RETURNING"
    " id, label, full_name, line1, line2, postal_code, city, country_code, phone_e164,"
    " ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon,"
    " is_default_shipping, created_at"
)

_DELETE_ADDRESS = text(
    "UPDATE addresses SET deleted_at = :now, is_default_shipping = false"
    " WHERE id = :id AND user_id = :user_id AND deleted_at IS NULL RETURNING id"
)

ADDRESS_FIELDS = (
    "label",
    "full_name",
    "line1",
    "line2",
    "postal_code",
    "city",
    "country_code",
    "phone_e164",
    "is_default_shipping",
)


async def list_addresses(db: AsyncSession, user_id: UUID) -> list[Row[Any]]:
    return list((await db.execute(_LIST_ADDRESSES, {"user_id": user_id})).all())


async def count_addresses(db: AsyncSession, user_id: UUID) -> int:
    return int(await db.scalar(_COUNT_ADDRESSES, {"user_id": user_id}) or 0)


async def clear_default_address(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(_CLEAR_DEFAULT_ADDRESS, {"user_id": user_id})


async def insert_address(db: AsyncSession, *, user_id: UUID, values: dict[str, Any]) -> Row[Any]:
    params = {"id": new_id(), "user_id": user_id, **values}
    return (await db.execute(_INSERT_ADDRESS, params)).one()


async def update_address(
    db: AsyncSession, *, user_id: UUID, address_id: UUID, changes: dict[str, Any]
) -> Row[Any] | None:
    params: dict[str, Any] = {"id": address_id, "user_id": user_id}
    for field in ADDRESS_FIELDS:
        params[f"set_{field}"] = field in changes
        params[field] = changes.get(field)
    params["set_location"] = "lat" in changes
    params["lat"], params["lon"] = changes.get("lat"), changes.get("lon")
    return (await db.execute(_UPDATE_ADDRESS, params)).one_or_none()


async def delete_address(
    db: AsyncSession, *, user_id: UUID, address_id: UUID, now: datetime
) -> bool:
    params = {"id": address_id, "user_id": user_id, "now": now}
    return (await db.execute(_DELETE_ADDRESS, params)).one_or_none() is not None


_LIST_ZONES = text(
    "SELECT"
    " id, label, place_name, ST_Y(center::geometry) AS lat,"
    " ST_X(center::geometry) AS lon, radius_m / 1000 AS radius_km, is_default"
    " FROM search_zones WHERE user_id = :user_id ORDER BY created_at, id"
)

_COUNT_ZONES = text("SELECT count(*) FROM search_zones WHERE user_id = :user_id")

_CLEAR_DEFAULT_ZONE = text(
    "UPDATE search_zones SET is_default = false WHERE user_id = :user_id AND is_default"
)

_INSERT_ZONE = text(
    "INSERT INTO search_zones (id, user_id, label, place_name, center, radius_m, is_default)"
    " VALUES (:id, :user_id, :label, :place_name,"
    " CASE WHEN CAST(:lat AS double precision) IS NULL THEN NULL"
    " ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision),"
    " CAST(:lat AS double precision)), 4326)::geography END, :radius_m, :is_default)"
    " RETURNING"
    " id, label, place_name, ST_Y(center::geometry) AS lat,"
    " ST_X(center::geometry) AS lon, radius_m / 1000 AS radius_km, is_default"
)

_UPDATE_ZONE = text(
    "UPDATE search_zones SET"
    " label = CASE WHEN :set_label THEN CAST(:label AS text) ELSE label END,"
    " place_name = CASE WHEN :set_place THEN CAST(:place_name AS text) ELSE place_name END,"
    " center = CASE WHEN :set_place THEN"
    " CASE WHEN CAST(:lat AS double precision) IS NULL THEN NULL"
    " ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision),"
    " CAST(:lat AS double precision)), 4326)::geography END ELSE center END,"
    " radius_m = CASE WHEN :set_radius THEN CAST(:radius_m AS integer) ELSE radius_m END,"
    " is_default = CASE WHEN :set_default THEN true ELSE is_default END"
    " WHERE id = :id AND user_id = :user_id RETURNING"
    " id, label, place_name, ST_Y(center::geometry) AS lat,"
    " ST_X(center::geometry) AS lon, radius_m / 1000 AS radius_km, is_default"
)

_ZONE_EXISTS = text(
    "SELECT EXISTS (SELECT 1 FROM search_zones WHERE id = :id AND user_id = :user_id)"
)

_DELETE_ZONE = text(
    "DELETE FROM search_zones WHERE id = :id AND user_id = :user_id RETURNING is_default"
)

_PROMOTE_OLDEST_ZONE = text(
    "UPDATE search_zones SET is_default = true WHERE id = ("
    " SELECT id FROM search_zones WHERE user_id = :user_id ORDER BY created_at, id LIMIT 1)"
)


async def list_zones(db: AsyncSession, user_id: UUID) -> list[Row[Any]]:
    return list((await db.execute(_LIST_ZONES, {"user_id": user_id})).all())


async def count_zones(db: AsyncSession, user_id: UUID) -> int:
    return int(await db.scalar(_COUNT_ZONES, {"user_id": user_id}) or 0)


async def zone_exists(db: AsyncSession, *, user_id: UUID, zone_id: UUID) -> bool:
    return bool(await db.scalar(_ZONE_EXISTS, {"id": zone_id, "user_id": user_id}))


async def clear_default_zone(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(_CLEAR_DEFAULT_ZONE, {"user_id": user_id})


async def insert_zone(db: AsyncSession, *, user_id: UUID, values: dict[str, Any]) -> Row[Any]:
    params = {"id": new_id(), "user_id": user_id, **values}
    return (await db.execute(_INSERT_ZONE, params)).one()


async def update_zone(
    db: AsyncSession, *, user_id: UUID, zone_id: UUID, changes: dict[str, Any]
) -> Row[Any] | None:
    params: dict[str, Any] = {
        "id": zone_id,
        "user_id": user_id,
        "set_label": "label" in changes,
        "label": changes.get("label"),
        "set_place": "place_name" in changes,
        "place_name": changes.get("place_name"),
        "lat": changes.get("lat"),
        "lon": changes.get("lon"),
        "set_radius": "radius_m" in changes,
        "radius_m": changes.get("radius_m"),
        "set_default": bool(changes.get("is_default")),
    }
    return (await db.execute(_UPDATE_ZONE, params)).one_or_none()


async def delete_zone(db: AsyncSession, *, user_id: UUID, zone_id: UUID) -> bool | None:
    """None when not found; otherwise whether the deleted zone was the default."""
    params = {"id": zone_id, "user_id": user_id}
    return (await db.execute(_DELETE_ZONE, params)).scalar_one_or_none()


async def promote_oldest_zone(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(_PROMOTE_OLDEST_ZONE, {"user_id": user_id})


# --- Preferences ----------------------------------------------------------------------------

_PREFERENCES = text(
    "SELECT interests, sizes, budget_max_minor, blocked_brands, feed_discovery_level,"
    " paused_categories, not_now_until, personalised_feed, notification_settings"
    " FROM user_preferences WHERE user_id = :user_id"
)

_SAVE_PREFERENCES = text(
    "INSERT INTO user_preferences (user_id, interests, sizes, budget_max_minor,"
    " blocked_brands, feed_discovery_level, paused_categories, not_now_until,"
    " personalised_feed, notification_settings)"
    " VALUES (:user_id, :interests, :sizes, :budget_max_minor, :blocked_brands,"
    " :feed_discovery_level, :paused_categories, :not_now_until, :personalised_feed,"
    " :notification_settings)"
    " ON CONFLICT (user_id) DO UPDATE SET interests = EXCLUDED.interests,"
    " sizes = EXCLUDED.sizes, budget_max_minor = EXCLUDED.budget_max_minor,"
    " blocked_brands = EXCLUDED.blocked_brands,"
    " feed_discovery_level = EXCLUDED.feed_discovery_level,"
    " paused_categories = EXCLUDED.paused_categories, not_now_until = EXCLUDED.not_now_until,"
    " personalised_feed = EXCLUDED.personalised_feed,"
    " notification_settings = EXCLUDED.notification_settings"
).bindparams(bindparam("sizes", type_=JSONB), bindparam("notification_settings", type_=JSONB))


async def preferences(db: AsyncSession, user_id: UUID) -> dict[str, Any] | None:
    row = (await db.execute(_PREFERENCES, {"user_id": user_id})).mappings().one_or_none()
    return dict(row) if row is not None else None


async def save_preferences(db: AsyncSession, *, user_id: UUID, values: dict[str, Any]) -> None:
    await db.execute(_SAVE_PREFERENCES, {"user_id": user_id, **values})


# --- GDPR export (ADR-0016) ------------------------------------------------------------------
# One statement per table, columns listed explicitly: secrets (token hashes, passkey keys) and
# other people's data never leave. `:u` is the person exporting.

EXPORT_QUERIES: dict[str, TextClause] = {
    "users": text(
        "SELECT id, email::text AS email, email_verified_at, phone_e164, phone_verified_at,"
        " username::text AS username, display_name, avatar_media_id, bio, locale, timezone,"
        " country_code, status::text AS status, visibility_factor, is_staff, birth_year,"
        " marketing_opt_in, last_seen_at, profile_completed_at, erasure_requested_at,"
        " created_at, updated_at FROM users WHERE id = :u"
    ),
    "auth_identities": text(
        "SELECT provider, provider_subject, created_at FROM auth_identities"
        " WHERE user_id = :u ORDER BY created_at"
    ),
    "passkeys": text(
        "SELECT id, name, transports, created_at, last_used_at FROM passkeys"
        " WHERE user_id = :u ORDER BY created_at"
    ),
    "sessions": text(
        "SELECT id, kind, created_at, last_used_at, expires_at, revoked_at, host(ip) AS ip,"
        " user_agent, device_label, country_code FROM sessions"
        " WHERE user_id = :u ORDER BY created_at"
    ),
    "user_roles": text(
        "SELECT role_key, granted_at FROM user_roles WHERE user_id = :u ORDER BY granted_at"
    ),
    # The payload may describe someone else: only the request's own fields.
    "approval_requests": text(
        "SELECT id, permission_key, status, reason, created_at, decided_at, expires_at,"
        " CASE WHEN requested_by = :u THEN 'requested' ELSE 'decided' END AS my_role"
        " FROM approval_requests WHERE requested_by = :u OR decided_by = :u"
        " ORDER BY created_at"
    ),
    "addresses": text(
        "SELECT id, label, full_name, line1, line2, postal_code, city, country_code,"
        " phone_e164, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon,"
        " is_default_shipping, created_at, updated_at, deleted_at FROM addresses"
        " WHERE user_id = :u ORDER BY created_at"
    ),
    "search_zones": text(
        "SELECT id, label, place_name, ST_Y(center::geometry) AS lat,"
        " ST_X(center::geometry) AS lon, radius_m, is_default, created_at, updated_at"
        " FROM search_zones WHERE user_id = :u ORDER BY created_at"
    ),
    "user_preferences": text(
        "SELECT interests, sizes, budget_max_minor, blocked_brands, feed_discovery_level,"
        " paused_categories, not_now_until, personalised_feed, notification_settings,"
        " updated_at FROM user_preferences WHERE user_id = :u"
    ),
    "consents": text(
        "SELECT purpose, granted, policy_version, source, anonymous_id, created_at"
        " FROM consents WHERE user_id = :u ORDER BY created_at"
    ),
    # Only the person's own blocks: who blocked them stays private.
    "blocks": text(
        "SELECT blocked_id, created_at FROM blocks WHERE blocker_id = :u ORDER BY created_at"
    ),
    "data_requests": text(
        "SELECT id, kind, status, refusal_reason, created_at, completed_at FROM data_requests"
        " WHERE user_id = :u ORDER BY created_at"
    ),
}

_EXPORT_FOLLOWING = text(
    "SELECT followee_user_id, followee_shop_id, created_at FROM follows"
    " WHERE follower_id = :u ORDER BY created_at"
)
# Followers are other people: counted, not named.
_EXPORT_FOLLOWERS_COUNT = text("SELECT count(*) FROM follows WHERE followee_user_id = :u")

_PENDING_REQUEST = text(
    "SELECT id FROM data_requests WHERE user_id = :u AND kind = :kind"
    " AND status IN ('received', 'processing')"
)
_INSERT_REQUEST = text(
    "INSERT INTO data_requests (id, user_id, kind, status, created_at)"
    " VALUES (:id, :u, :kind, 'received', :now)"
)
_REQUEST_FOR_BUILD = text(
    "SELECT r.user_id, r.status, u.email::text AS email FROM data_requests r"
    " JOIN users u ON u.id = r.user_id WHERE r.id = :id AND r.kind = 'export' FOR UPDATE OF r"
)
_INSERT_EXPORT = text(
    "INSERT INTO data_exports (id, data_request_id, ciphertext, expires_at, created_at)"
    " VALUES (:id, :request_id, :ciphertext, :expires_at, :now)"
)
_COMPLETE_REQUEST = text(
    "UPDATE data_requests SET status = 'completed', completed_at = :now WHERE id = :id"
)
_LIST_REQUESTS = text(
    "SELECT r.id, r.kind, r.status, r.created_at, r.completed_at, e.expires_at"
    " FROM data_requests r LEFT JOIN data_exports e ON e.data_request_id = r.id"
    " WHERE r.user_id = :u ORDER BY r.created_at DESC"
)
_EXPORT_CIPHERTEXT = text(
    "SELECT e.ciphertext FROM data_exports e JOIN data_requests r ON r.id = e.data_request_id"
    " WHERE r.id = :id AND r.user_id = :u AND e.expires_at > :now"
)
_PURGE_EXPORTS = text("DELETE FROM data_exports WHERE expires_at <= :now")


async def export_rows(db: AsyncSession, query: TextClause, user_id: UUID) -> list[dict[str, Any]]:
    return [dict(row) for row in (await db.execute(query, {"u": user_id})).mappings()]


async def export_follows(db: AsyncSession, user_id: UUID) -> dict[str, Any]:
    return {
        "following": await export_rows(db, _EXPORT_FOLLOWING, user_id),
        "followers_count": int(await db.scalar(_EXPORT_FOLLOWERS_COUNT, {"u": user_id}) or 0),
    }


async def pending_data_request(db: AsyncSession, user_id: UUID, kind: str) -> UUID | None:
    return await db.scalar(_PENDING_REQUEST, {"u": user_id, "kind": kind})


async def insert_data_request(
    db: AsyncSession, *, request_id: UUID, user_id: UUID, kind: str, now: datetime
) -> None:
    await db.execute(_INSERT_REQUEST, {"id": request_id, "u": user_id, "kind": kind, "now": now})


async def export_request_for_build(db: AsyncSession, request_id: UUID) -> Row[Any] | None:
    return (await db.execute(_REQUEST_FOR_BUILD, {"id": request_id})).one_or_none()


async def store_export(
    db: AsyncSession, *, request_id: UUID, ciphertext: bytes, expires_at: datetime, now: datetime
) -> None:
    await db.execute(
        _INSERT_EXPORT,
        {
            "id": new_id(),
            "request_id": request_id,
            "ciphertext": ciphertext,
            "expires_at": expires_at,
            "now": now,
        },
    )
    await db.execute(_COMPLETE_REQUEST, {"id": request_id, "now": now})


async def list_data_requests(db: AsyncSession, user_id: UUID) -> list[Row[Any]]:
    return list((await db.execute(_LIST_REQUESTS, {"u": user_id})).all())


async def export_ciphertext(
    db: AsyncSession, *, request_id: UUID, user_id: UUID, now: datetime
) -> bytes | None:
    value = await db.scalar(_EXPORT_CIPHERTEXT, {"id": request_id, "u": user_id, "now": now})
    return bytes(value) if value is not None else None


async def purge_expired_exports(db: AsyncSession, *, now: datetime) -> int:
    result = await db.execute(_PURGE_EXPORTS, {"now": now})
    return result.rowcount  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]


# --- GDPR erasure (P1-T09b) ------------------------------------------------------------------

_REQUEST_ERASURE = text(
    "UPDATE users SET erasure_requested_at = coalesce(erasure_requested_at, :now)"
    " WHERE id = :u AND status <> 'deleted' RETURNING erasure_requested_at"
)
_CANCEL_ERASURE = text(
    "UPDATE users SET erasure_requested_at = NULL"
    " WHERE id = :u AND erasure_requested_at IS NOT NULL AND status <> 'deleted' RETURNING id"
)
_CLOSE_ERASURE_REQUEST = text(
    "UPDATE data_requests SET status = :status, refusal_reason = :reason, completed_at = :now"
    " WHERE user_id = :u AND kind = 'erasure' AND status IN ('received', 'processing')"
)
_DUE_ERASURES = text(
    "SELECT id FROM users WHERE erasure_requested_at <= :cutoff AND status <> 'deleted'"
    " ORDER BY erasure_requested_at LIMIT :limit"
)
_LOCK_DUE_ERASURE = text(
    "SELECT email::text AS email FROM users WHERE id = :u AND erasure_requested_at <= :cutoff"
    " AND status <> 'deleted' FOR UPDATE SKIP LOCKED"
)
# What the identity module holds about the person, in dependency order. Consents stay as proof
# with the internal identifier only; data requests stay as proof the rights were exercised.
ERASE_IDENTITY: tuple[TextClause, ...] = (
    text("DELETE FROM magic_links WHERE email = (SELECT email FROM users WHERE id = :u)"),
    text("DELETE FROM sessions WHERE user_id = :u"),
    text("DELETE FROM auth_identities WHERE user_id = :u"),
    text("DELETE FROM passkeys WHERE user_id = :u"),
    text("DELETE FROM addresses WHERE user_id = :u"),
    text("DELETE FROM search_zones WHERE user_id = :u"),
    text("DELETE FROM user_preferences WHERE user_id = :u"),
    text("DELETE FROM user_roles WHERE user_id = :u"),
    text("DELETE FROM follows WHERE follower_id = :u OR followee_user_id = :u"),
    text("DELETE FROM blocks WHERE blocker_id = :u OR blocked_id = :u"),
    text(
        "DELETE FROM data_exports WHERE data_request_id IN"
        " (SELECT id FROM data_requests WHERE user_id = :u)"
    ),
    text("DELETE FROM idempotency_keys WHERE user_id = :u"),
    text("UPDATE consents SET anonymous_id = NULL WHERE user_id = :u"),
)
_ANONYMISE_USER = text(
    "UPDATE users SET email = 'efface+' || replace(CAST(:u AS text), '-', '') || '@invalid',"
    " email_verified_at = NULL, phone_e164 = NULL, phone_verified_at = NULL,"
    " username = 'efface_' || right(replace(CAST(:u AS text), '-', ''), 8),"
    " display_name = 'Compte supprimé', avatar_media_id = NULL, bio = NULL,"
    " birth_year = NULL, marketing_opt_in = false, last_seen_at = NULL,"
    " status = 'deleted', deleted_at = :now WHERE id = :u"
)


async def request_erasure(db: AsyncSession, *, user_id: UUID, now: datetime) -> datetime | None:
    """The date of the request (the first one stands); None for an erased account."""
    return await db.scalar(_REQUEST_ERASURE, {"u": user_id, "now": now})


async def cancel_erasure(db: AsyncSession, *, user_id: UUID, now: datetime) -> bool:
    if (await db.execute(_CANCEL_ERASURE, {"u": user_id})).one_or_none() is None:
        return False
    await db.execute(
        _CLOSE_ERASURE_REQUEST,
        {"u": user_id, "status": "refused", "reason": "cancelled_by_user", "now": now},
    )
    return True


async def due_erasures(db: AsyncSession, *, cutoff: datetime, limit: int) -> list[UUID]:
    return list((await db.scalars(_DUE_ERASURES, {"cutoff": cutoff, "limit": limit})).all())


async def lock_due_erasure(db: AsyncSession, *, user_id: UUID, cutoff: datetime) -> bool:
    """True when the account is still due and this worker holds it."""
    row = (await db.execute(_LOCK_DUE_ERASURE, {"u": user_id, "cutoff": cutoff})).one_or_none()
    return row is not None


async def erase_identity(db: AsyncSession, user_id: UUID) -> None:
    for statement in ERASE_IDENTITY:
        await db.execute(statement, {"u": user_id})


async def anonymise_user(db: AsyncSession, *, user_id: UUID, now: datetime) -> None:
    await db.execute(_ANONYMISE_USER, {"u": user_id, "now": now})
    await db.execute(
        _CLOSE_ERASURE_REQUEST,
        {"u": user_id, "status": "completed", "reason": None, "now": now},
    )
