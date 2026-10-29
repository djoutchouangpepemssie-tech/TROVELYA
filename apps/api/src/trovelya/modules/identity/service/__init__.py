"""Public interface of the identity module: other modules import from here only (5.4)."""

from trovelya.modules.identity.service.access import expire_approvals
from trovelya.modules.identity.service.alerts import identity_subscriptions
from trovelya.modules.identity.service.auth import (
    clear_session_cookie,
    current_user,
    get_clock,
    get_session_policy,
    optional_user,
    set_session_cookie,
)
from trovelya.modules.identity.service.gdpr import (
    EXPORT_JOB,
    build_data_export,
    process_erasures,
    purge_expired_exports,
)
from trovelya.modules.identity.service.magic_links import (
    SignIn,
    magic_link_ttl_min,
    purge_expired_magic_links,
    request_magic_link,
    verify_magic_link,
)
from trovelya.modules.identity.service.magic_links import (
    limit_requests as limit_magic_link_requests,
)
from trovelya.modules.identity.service.places import MemberPlace, PlaceSource, member_place
from trovelya.modules.identity.service.profile import default_zone_center, public_seller
from trovelya.modules.identity.service.sessions import (
    CurrentUser,
    IssuedSession,
    SessionPolicy,
    SessionSummary,
    create_session,
    list_sessions,
    resolve_session,
    revoke_other_sessions,
    revoke_session,
    rotate_session,
)

__all__ = [
    "EXPORT_JOB",
    "CurrentUser",
    "IssuedSession",
    "MemberPlace",
    "PlaceSource",
    "SessionPolicy",
    "SessionSummary",
    "SignIn",
    "build_data_export",
    "clear_session_cookie",
    "create_session",
    "current_user",
    "default_zone_center",
    "expire_approvals",
    "get_clock",
    "get_session_policy",
    "identity_subscriptions",
    "limit_magic_link_requests",
    "list_sessions",
    "magic_link_ttl_min",
    "member_place",
    "optional_user",
    "process_erasures",
    "public_seller",
    "purge_expired_exports",
    "purge_expired_magic_links",
    "request_magic_link",
    "resolve_session",
    "revoke_other_sessions",
    "revoke_session",
    "rotate_session",
    "set_session_cookie",
    "verify_magic_link",
]
