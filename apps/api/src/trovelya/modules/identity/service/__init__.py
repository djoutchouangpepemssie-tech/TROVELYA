"""Public interface of the identity module: other modules import from here only (5.4)."""

from trovelya.modules.identity.service.auth import (
    clear_session_cookie,
    current_user,
    get_clock,
    get_session_policy,
    optional_user,
    set_session_cookie,
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
    "clear_session_cookie",
    "create_session",
    "current_user",
    "get_clock",
    "get_session_policy",
    "list_sessions",
    "optional_user",
    "resolve_session",
    "revoke_other_sessions",
    "revoke_session",
    "rotate_session",
    "set_session_cookie",
]
