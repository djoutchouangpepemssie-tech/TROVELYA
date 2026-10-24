"""Public interface of the identity module: other modules import from here only (5.4)."""

from trovelya.modules.identity.service.alerts import identity_subscriptions
from trovelya.modules.identity.service.auth import (
    clear_session_cookie,
    current_user,
    get_clock,
    get_session_policy,
    optional_user,
    set_session_cookie,
)
from trovelya.modules.identity.service.magic_links import (
    SignIn,
    purge_expired_magic_links,
    request_magic_link,
    verify_magic_link,
)
from trovelya.modules.identity.service.magic_links import (
    limit_requests as limit_magic_link_requests,
)
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
    "CurrentUser",
    "IssuedSession",
    "SessionPolicy",
    "SessionSummary",
    "SignIn",
    "clear_session_cookie",
    "create_session",
    "current_user",
    "get_clock",
    "get_session_policy",
    "identity_subscriptions",
    "limit_magic_link_requests",
    "list_sessions",
    "optional_user",
    "purge_expired_magic_links",
    "request_magic_link",
    "resolve_session",
    "revoke_other_sessions",
    "revoke_session",
    "rotate_session",
    "set_session_cookie",
    "verify_magic_link",
]
