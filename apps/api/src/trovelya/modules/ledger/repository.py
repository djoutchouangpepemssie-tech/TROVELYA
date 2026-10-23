"""SQL access for the ledger module. Only `service.py` may use it (section 5.4)."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from trovelya.modules.ledger.models import EntryInput, LedgerAccountType


async def insert_account_if_absent(
    session: AsyncSession,
    *,
    account_id: UUID,
    code: str,
    type: LedgerAccountType,  # noqa: A002 — column name
    currency: str,
    description: str,
    owner_user_id: UUID | None,
) -> UUID:
    await session.execute(
        text(
            "INSERT INTO ledger_accounts (id, code, type, currency, owner_user_id, description)"
            " VALUES (:id, :code, CAST(:type AS ledger_account_type), :currency, :owner,"
            " :description)"
            " ON CONFLICT (code) DO NOTHING"
        ),
        {
            "id": account_id,
            "code": code,
            "type": type.value,
            "currency": currency,
            "owner": owner_user_id,
            "description": description,
        },
    )
    found = await session.scalar(
        text("SELECT id FROM ledger_accounts WHERE code = :code"), {"code": code}
    )
    if found is None:  # unreachable: inserted or already present
        raise LookupError(code)
    return found


async def account_currencies(session: AsyncSession, account_ids: Sequence[UUID]) -> dict[UUID, str]:
    rows = await session.execute(
        text("SELECT id, currency FROM ledger_accounts WHERE id = ANY(:ids)"),
        {"ids": list(account_ids)},
    )
    return {row.id: row.currency for row in rows}


async def insert_transaction_if_absent(
    session: AsyncSession,
    *,
    transaction_id: UUID,
    kind: str,
    reference_type: str,
    reference_id: UUID,
    idempotency_key: str,
    description: str,
    created_by: str,
) -> bool:
    """True if inserted; False if the key exists (waits for a concurrent insert to finish)."""
    inserted = await session.scalar(
        text(
            "INSERT INTO ledger_transactions"
            " (id, kind, reference_type, reference_id, idempotency_key, description, created_by)"
            " VALUES (:id, :kind, :reference_type, :reference_id, :key, :description, :created_by)"
            " ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"
        ),
        {
            "id": transaction_id,
            "kind": kind,
            "reference_type": reference_type,
            "reference_id": reference_id,
            "key": idempotency_key,
            "description": description,
            "created_by": created_by,
        },
    )
    return inserted is not None


async def insert_entries(
    session: AsyncSession, transaction_id: UUID, entries: Sequence[EntryInput]
) -> None:
    await session.execute(
        text(
            "INSERT INTO ledger_entries"
            " (transaction_id, account_id, direction, amount_minor, currency)"
            " VALUES (:transaction_id, :account_id, :direction, :amount_minor, :currency)"
        ),
        [
            {
                "transaction_id": transaction_id,
                "account_id": entry.account_id,
                "direction": entry.direction,
                "amount_minor": entry.amount.amount_minor,
                "currency": entry.amount.currency,
            }
            for entry in entries
        ],
    )


async def find_transaction(
    session: AsyncSession, idempotency_key: str
) -> Row[tuple[UUID, str, str, UUID]] | None:
    return (
        await session.execute(
            text(
                "SELECT id, kind, reference_type, reference_id FROM ledger_transactions"
                " WHERE idempotency_key = :key"
            ),
            {"key": idempotency_key},
        )
    ).one_or_none()


async def transaction_entries(
    session: AsyncSession, transaction_id: UUID
) -> list[tuple[UUID, str, int, str]]:
    rows = await session.execute(
        text(
            "SELECT account_id, direction, amount_minor, currency FROM ledger_entries"
            " WHERE transaction_id = :t"
        ),
        {"t": transaction_id},
    )
    return [(row.account_id, row.direction, row.amount_minor, row.currency) for row in rows]


async def balance(session: AsyncSession, account_id: UUID, currency: str) -> int:
    total = await session.scalar(
        text(
            "SELECT coalesce(sum("
            "CASE direction WHEN 'D' THEN amount_minor ELSE -amount_minor END), 0)"
            " FROM ledger_entries WHERE account_id = :a AND currency = :c"
        ),
        {"a": account_id, "c": currency},
    )
    return int(total or 0)
