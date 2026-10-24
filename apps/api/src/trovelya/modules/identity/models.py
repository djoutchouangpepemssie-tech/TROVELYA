"""Identity value types (section 7.3). Rows are read and written with SQL in repository.py."""

from enum import StrEnum
from typing import Literal

SessionKind = Literal["web", "mobile", "admin"]
MagicLinkPurpose = Literal["login", "verify_email", "change_email", "step_up"]
OAuthProvider = Literal["google", "apple"]


class UserStatus(StrEnum):
    ACTIVE = "active"
    RESTRICTED = "restricted"
    SUSPENDED = "suspended"
    BANNED = "banned"
    DELETED = "deleted"


# Accounts in these states cannot hold a session (section 8.13 sanctions, GDPR erasure).
BLOCKED_STATUSES = frozenset({UserStatus.SUSPENDED, UserStatus.BANNED, UserStatus.DELETED})
