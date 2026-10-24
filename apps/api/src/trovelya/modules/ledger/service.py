"""Ledger service: the only entry point for other modules (section 5.4).

Functions write in the caller's transaction and never commit. The database is the final
guarantee (deferred balance check, immutability); the checks here give clear errors first.
"""

from collections import Counter, defaultdict
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.ledger import repository
from trovelya.modules.ledger.errors import (
    LedgerCurrencyMismatchError,
    LedgerIdempotencyConflictError,
    LedgerUnbalancedError,
)
from trovelya.modules.ledger.models import EntryInput, LedgerAccountType, PostedTransaction
from trovelya.shared.ids import new_id
from trovelya.shared.money import Money

__all__ = [
    "EntryInput",
    "LedgerAccountType",
    "PostedTransaction",
    "account_balance",
    "get_or_create_account",
    "post_transaction",
]


async def get_or_create_account(
    session: AsyncSession,
    *,
    code: str,
    type: LedgerAccountType,  # noqa: A002 — column name
    currency: str,
    description: str,
    owner_user_id: UUID | None = None,
) -> UUID:
    Money.zero(currency)  # validates the ISO 4217 code
    return await repository.insert_account_if_absent(
        session,
        account_id=new_id(),
        code=code,
        type=type,
        currency=currency,
        description=description,
        owner_user_id=owner_user_id,
    )


def _check_balanced(entries: Sequence[EntryInput]) -> None:
    if len(entries) < 2:
        raise LedgerUnbalancedError("a transaction needs at least two entries")
    totals: defaultdict[str, int] = defaultdict(int)
    for entry in entries:
        sign = 1 if entry.direction == "D" else -1
        totals[entry.amount.currency] += sign * entry.amount.amount_minor
    unbalanced = sorted(currency for currency, total in totals.items() if total != 0)
    if unbalanced:
        raise LedgerUnbalancedError(f"debits and credits differ in {', '.join(unbalanced)}")


def _fingerprint(
    entries: Sequence[tuple[UUID, str, int, str]],
) -> Counter[tuple[UUID, str, int, str]]:
    return Counter(entries)


async def post_transaction(
    session: AsyncSession,
    *,
    kind: str,
    reference_type: str,
    reference_id: UUID,
    idempotency_key: str,
    description: str,
    entries: Sequence[EntryInput],
    created_by: str = "system",
) -> PostedTransaction:
    """Post a balanced transaction, exactly once per idempotency key.

    Same key and same content → the existing transaction (`replayed=True`), nothing written.
    Same key, different content → `LedgerIdempotencyConflictError`.
    """
    _check_balanced(entries)
    currencies = await repository.account_currencies(session, [e.account_id for e in entries])
    for entry in entries:
        if currencies.get(entry.account_id) != entry.amount.currency:
            raise LedgerCurrencyMismatchError(
                f"account {entry.account_id} does not hold {entry.amount.currency}"
            )

    requested = _fingerprint(
        [(e.account_id, e.direction, e.amount.amount_minor, e.amount.currency) for e in entries]
    )
    transaction_id = new_id()
    inserted = await repository.insert_transaction_if_absent(
        session,
        transaction_id=transaction_id,
        kind=kind,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        description=description,
        created_by=created_by,
    )
    if inserted:
        await repository.insert_entries(session, transaction_id, entries)
        return PostedTransaction(id=transaction_id, replayed=False)

    existing = await repository.find_transaction(session, idempotency_key)
    if existing is None:  # unreachable: the conflicting row is committed and visible
        raise LedgerIdempotencyConflictError(idempotency_key)
    same_header = (existing.kind, existing.reference_type, existing.reference_id) == (
        kind,
        reference_type,
        reference_id,
    )
    stored = _fingerprint(await repository.transaction_entries(session, existing.id))
    if not same_header or stored != requested:
        raise LedgerIdempotencyConflictError(idempotency_key)
    return PostedTransaction(id=existing.id, replayed=True)


async def account_balance(session: AsyncSession, account_id: UUID, currency: str) -> Money:
    """Debit balance (debits minus credits) of an account, computed directly from entries."""
    return Money(await repository.balance(session, account_id, currency), currency)
