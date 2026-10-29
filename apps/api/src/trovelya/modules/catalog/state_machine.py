"""The listing state machine (section 9.1, with plan Q29 and Q32): an explicit table of
transitions, tested exhaustively. Applying a transition (history, event) is service/states.py's job.

Publishing has two events: `publish` puts a low-risk listing online at once, `submit_for_review`
sends it to moderation (P2-T05b decides which). Reserving, releasing and selling are in the
table for P4 and have no route yet.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from trovelya.modules.catalog.models import ListingStatus


class ListingEvent(StrEnum):
    PUBLISH = "publish"
    SUBMIT_FOR_REVIEW = "submit_for_review"
    APPROVE = "approve"
    REJECT = "reject"
    RESERVE = "reserve"
    RELEASE = "release"
    SELL = "sell"
    WITHDRAW = "withdraw"
    REPUBLISH = "republish"
    REMOVE = "remove"
    APPEAL_ACCEPTED = "appeal_accepted"
    EXPIRE = "expire"
    RENEW = "renew"


_S, _E = ListingStatus, ListingEvent

TRANSITIONS: Mapping[tuple[ListingStatus, ListingEvent], ListingStatus] = MappingProxyType(
    {
        (_S.DRAFT, _E.PUBLISH): _S.ACTIVE,
        (_S.DRAFT, _E.SUBMIT_FOR_REVIEW): _S.PENDING_REVIEW,
        (_S.PENDING_REVIEW, _E.APPROVE): _S.ACTIVE,
        (_S.PENDING_REVIEW, _E.REJECT): _S.REMOVED,
        (_S.ACTIVE, _E.RESERVE): _S.RESERVED,
        (_S.RESERVED, _E.RELEASE): _S.ACTIVE,
        (_S.RESERVED, _E.SELL): _S.SOLD,
        (_S.ACTIVE, _E.WITHDRAW): _S.WITHDRAWN,
        (_S.WITHDRAWN, _E.REPUBLISH): _S.ACTIVE,
        (_S.ACTIVE, _E.REMOVE): _S.REMOVED,
        (_S.REMOVED, _E.APPEAL_ACCEPTED): _S.ACTIVE,
        (_S.ACTIVE, _E.EXPIRE): _S.EXPIRED,
        (_S.EXPIRED, _E.RENEW): _S.ACTIVE,
        # Q29: the seller takes back a listing awaiting moderation.
        (_S.PENDING_REVIEW, _E.WITHDRAW): _S.WITHDRAWN,
        # Q32: putting a listing back online goes through the moderation too.
        (_S.WITHDRAWN, _E.SUBMIT_FOR_REVIEW): _S.PENDING_REVIEW,
        (_S.EXPIRED, _E.SUBMIT_FOR_REVIEW): _S.PENDING_REVIEW,
    }
)


class InvalidTransition(Exception):  # noqa: N818 — the name section 9 gives it
    def __init__(self, status: ListingStatus, event: ListingEvent) -> None:
        super().__init__(f"{event} is not allowed from {status}")
        self.status = status
        self.event = event


def next_status(status: ListingStatus, event: ListingEvent) -> ListingStatus:
    """Where `event` leads from `status`; `InvalidTransition` when the table says nowhere."""
    try:
        return TRANSITIONS[(status, event)]
    except KeyError:
        raise InvalidTransition(status, event) from None
