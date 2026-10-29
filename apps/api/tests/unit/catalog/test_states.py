"""The listing state machine (section 9.1, plan P2-T04): every pair (status, event) is either
in the table or refused with `InvalidTransition`, never anything else."""

import itertools

import pytest

from trovelya.modules.catalog.models import ListingStatus as S
from trovelya.modules.catalog.state_machine import (
    TRANSITIONS,
    InvalidTransition,
    next_status,
)
from trovelya.modules.catalog.state_machine import (
    ListingEvent as E,
)

ALLOWED = {
    (S.DRAFT, E.PUBLISH): S.ACTIVE,
    (S.DRAFT, E.SUBMIT_FOR_REVIEW): S.PENDING_REVIEW,
    (S.PENDING_REVIEW, E.APPROVE): S.ACTIVE,
    (S.PENDING_REVIEW, E.REJECT): S.REMOVED,
    (S.ACTIVE, E.RESERVE): S.RESERVED,
    (S.RESERVED, E.RELEASE): S.ACTIVE,
    (S.RESERVED, E.SELL): S.SOLD,
    (S.ACTIVE, E.WITHDRAW): S.WITHDRAWN,
    (S.WITHDRAWN, E.REPUBLISH): S.ACTIVE,
    (S.ACTIVE, E.REMOVE): S.REMOVED,
    (S.REMOVED, E.APPEAL_ACCEPTED): S.ACTIVE,
    (S.ACTIVE, E.EXPIRE): S.EXPIRED,
    (S.EXPIRED, E.RENEW): S.ACTIVE,
}


def test_transition_table_exhaustive() -> None:
    """All 8 statuses by all events: the allowed ones lead where section 9.1 says, every other
    one is refused."""
    assert dict(TRANSITIONS) == ALLOWED
    for status, event in itertools.product(S, E):
        if (status, event) in ALLOWED:
            assert next_status(status, event) is ALLOWED[(status, event)]
        else:
            with pytest.raises(InvalidTransition):
                next_status(status, event)


def test_sold_and_removed_never_back_to_active() -> None:
    """Section 9.1: only an accepted appeal brings a removed listing back; a sold one is final."""
    assert not any(status is S.SOLD for status, _ in TRANSITIONS)
    back = [event for status, event in TRANSITIONS if status is S.REMOVED]
    assert back == [E.APPEAL_ACCEPTED]


def test_every_event_is_used() -> None:
    assert {event for _, event in TRANSITIONS} == set(E)
