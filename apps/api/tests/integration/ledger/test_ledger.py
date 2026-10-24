"""Double-entry ledger skeleton (section 7.8, invariants 10.5)."""

import itertools
from collections.abc import Sequence
from uuid import UUID

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.ledger.conftest import LoopThread
from trovelya.core.db import commit
from trovelya.modules.ledger.errors import (
    LedgerCurrencyMismatchError,
    LedgerIdempotencyConflictError,
    LedgerUnbalancedError,
)
from trovelya.modules.ledger.service import (
    EntryInput,
    LedgerAccountType,
    account_balance,
    get_or_create_account,
    post_transaction,
)
from trovelya.shared.ids import new_id
from trovelya.shared.money import Money

SM = async_sessionmaker[AsyncSession]


async def _accounts(sm: SM, currency: str = "EUR") -> tuple[UUID, UUID]:
    async with sm() as session:
        clearing = await get_or_create_account(
            session,
            code=f"asset:test:{new_id()}",
            type=LedgerAccountType.ASSET,
            currency=currency,
            description="test asset",
        )
        seller = await get_or_create_account(
            session,
            code=f"liability:test:{new_id()}",
            type=LedgerAccountType.LIABILITY,
            currency=currency,
            description="test liability",
        )
        await commit(session)
    return clearing, seller


def _eur(amount: int) -> Money:
    return Money(amount, "EUR")


async def _raw_transaction(session: AsyncSession) -> UUID:
    transaction_id = new_id()
    await session.execute(
        text(
            "INSERT INTO ledger_transactions (id, kind, reference_type, reference_id,"
            " idempotency_key, description, created_by)"
            " VALUES (:id, 'adjustment', 'test', :id, :key, 'raw', 'system')"
        ),
        {"id": transaction_id, "key": f"raw:{transaction_id}"},
    )
    return transaction_id


async def _raw_entry(
    session: AsyncSession,
    transaction_id: UUID,
    account_id: UUID,
    direction: str,
    amount: int,
    currency: str = "EUR",
) -> None:
    await session.execute(
        text(
            "INSERT INTO ledger_entries"
            " (transaction_id, account_id, direction, amount_minor, currency)"
            " VALUES (:t, :a, :d, :m, :c)"
        ),
        {"t": transaction_id, "a": account_id, "d": direction, "m": amount, "c": currency},
    )


async def test_unbalanced_rejected_at_commit(sessionmaker: SM) -> None:
    clearing, _ = await _accounts(sessionmaker)
    async with sessionmaker() as session:
        transaction_id = await _raw_transaction(session)
        await _raw_entry(session, transaction_id, clearing, "D", 100)
        await _raw_entry(session, transaction_id, clearing, "C", 60)
        # The INSERTs succeed: the balance check is deferred to COMMIT.
        with pytest.raises(DBAPIError, match="unbalanced"):
            await session.commit()


async def test_balanced_with_temporary_imbalance_commits(sessionmaker: SM) -> None:
    clearing, seller = await _accounts(sessionmaker)
    async with sessionmaker() as session:
        transaction_id = await _raw_transaction(session)
        await _raw_entry(session, transaction_id, clearing, "D", 100)
        await _raw_entry(session, transaction_id, seller, "C", 60)
        await _raw_entry(session, transaction_id, seller, "C", 40)
        await session.commit()


async def test_multi_currency_each_balanced(sessionmaker: SM) -> None:
    eur_a, eur_b = await _accounts(sessionmaker, "EUR")
    pln_a, _ = await _accounts(sessionmaker, "PLN")
    async with sessionmaker() as session:
        transaction_id = await _raw_transaction(session)
        await _raw_entry(session, transaction_id, eur_a, "D", 100)
        await _raw_entry(session, transaction_id, eur_b, "C", 100)
        await _raw_entry(session, transaction_id, pln_a, "D", 50, "PLN")
        with pytest.raises(DBAPIError, match="unbalanced"):
            await session.commit()


async def test_transaction_without_entries_rejected(sessionmaker: SM) -> None:
    async with sessionmaker() as session:
        await _raw_transaction(session)
        with pytest.raises(DBAPIError, match="at least two entries"):
            await session.commit()


async def test_transaction_with_single_entry_rejected(sessionmaker: SM) -> None:
    clearing, _ = await _accounts(sessionmaker)
    async with sessionmaker() as session:
        transaction_id = await _raw_transaction(session)
        await _raw_entry(session, transaction_id, clearing, "D", 0 + 1)
        with pytest.raises(DBAPIError):
            await session.commit()


async def test_entry_currency_must_match_account(sessionmaker: SM) -> None:
    clearing, _ = await _accounts(sessionmaker, "EUR")
    async with sessionmaker() as session:
        transaction_id = await _raw_transaction(session)
        with pytest.raises(DBAPIError, match="currency"):
            await _raw_entry(session, transaction_id, clearing, "D", 100, "PLN")


async def test_non_positive_amount_rejected(sessionmaker: SM) -> None:
    clearing, _ = await _accounts(sessionmaker)
    async with sessionmaker() as session:
        transaction_id = await _raw_transaction(session)
        with pytest.raises(DBAPIError):
            await _raw_entry(session, transaction_id, clearing, "D", 0)


async def _post(
    sm: SM, key: str, entries: Sequence[EntryInput], reference_id: UUID | None = None
) -> tuple[UUID, bool]:
    async with sm() as session:
        posted = await post_transaction(
            session,
            kind="adjustment",
            reference_type="test",
            reference_id=reference_id or new_id(),
            idempotency_key=key,
            description="test",
            entries=entries,
        )
        await commit(session)
    return posted.id, posted.replayed


async def test_entries_immutable(sessionmaker: SM) -> None:
    clearing, seller = await _accounts(sessionmaker)
    transaction_id, _ = await _post(
        sessionmaker,
        f"imm:{new_id()}",
        [EntryInput(clearing, "D", _eur(100)), EntryInput(seller, "C", _eur(100))],
    )
    for statement in (
        "UPDATE ledger_entries SET amount_minor = 1 WHERE transaction_id = :t",
        "DELETE FROM ledger_entries WHERE transaction_id = :t",
        "UPDATE ledger_transactions SET description = 'x' WHERE id = :t",
        "DELETE FROM ledger_transactions WHERE id = :t",
    ):
        with pytest.raises(DBAPIError, match="immutable"):
            async with sessionmaker() as session:
                await session.execute(text(statement), {"t": transaction_id})
                await session.commit()


async def test_idempotent_replay_no_duplicate(sessionmaker: SM) -> None:
    clearing, seller = await _accounts(sessionmaker)
    key = f"replay:{new_id()}"
    reference = new_id()
    entries = [EntryInput(clearing, "D", _eur(2592)), EntryInput(seller, "C", _eur(2592))]
    first_id, first_replayed = await _post(sessionmaker, key, entries, reference)
    second_id, second_replayed = await _post(sessionmaker, key, list(reversed(entries)), reference)
    assert (first_replayed, second_replayed) == (False, True)
    assert first_id == second_id
    async with sessionmaker() as session:
        transactions = await session.scalar(
            text("SELECT count(*) FROM ledger_transactions WHERE idempotency_key = :k"), {"k": key}
        )
        entry_count = await session.scalar(
            text("SELECT count(*) FROM ledger_entries WHERE transaction_id = :t"), {"t": first_id}
        )
    assert (transactions, entry_count) == (1, 2)


async def test_idempotency_conflict(sessionmaker: SM) -> None:
    clearing, seller = await _accounts(sessionmaker)
    key = f"conflict:{new_id()}"
    reference = new_id()
    await _post(
        sessionmaker,
        key,
        [EntryInput(clearing, "D", _eur(100)), EntryInput(seller, "C", _eur(100))],
        reference,
    )
    with pytest.raises(LedgerIdempotencyConflictError):
        await _post(
            sessionmaker,
            key,
            [EntryInput(clearing, "D", _eur(200)), EntryInput(seller, "C", _eur(200))],
            reference,
        )


async def test_service_rejects_unbalanced_before_db(sessionmaker: SM) -> None:
    clearing, seller = await _accounts(sessionmaker)
    async with sessionmaker() as session:
        with pytest.raises(LedgerUnbalancedError):
            await post_transaction(
                session,
                kind="adjustment",
                reference_type="test",
                reference_id=new_id(),
                idempotency_key=f"unbal:{new_id()}",
                description="test",
                entries=[EntryInput(clearing, "D", _eur(100)), EntryInput(seller, "C", _eur(99))],
            )


async def test_service_rejects_currency_not_matching_account(sessionmaker: SM) -> None:
    clearing, seller = await _accounts(sessionmaker, "EUR")
    async with sessionmaker() as session:
        with pytest.raises(LedgerCurrencyMismatchError):
            await post_transaction(
                session,
                kind="adjustment",
                reference_type="test",
                reference_id=new_id(),
                idempotency_key=f"cur:{new_id()}",
                description="test",
                entries=[
                    EntryInput(clearing, "D", Money(100, "PLN")),
                    EntryInput(seller, "C", Money(100, "PLN")),
                ],
            )


async def test_entry_amount_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        EntryInput(new_id(), "D", _eur(0))
    with pytest.raises(ValueError, match="direction"):
        EntryInput(new_id(), "X", _eur(1))  # type: ignore[arg-type]


async def test_account_balance(sessionmaker: SM) -> None:
    clearing, seller = await _accounts(sessionmaker)
    await _post(
        sessionmaker,
        f"bal:{new_id()}",
        [EntryInput(clearing, "D", _eur(25920)), EntryInput(seller, "C", _eur(25920))],
    )
    async with sessionmaker() as session:
        assert await account_balance(session, clearing, "EUR") == _eur(25920)
        assert await account_balance(session, seller, "EUR") == _eur(-25920)


async def test_get_or_create_account_is_idempotent(sessionmaker: SM) -> None:
    code = f"asset:test:{new_id()}"
    async with sessionmaker() as session:
        first = await get_or_create_account(
            session, code=code, type=LedgerAccountType.ASSET, currency="EUR", description="d"
        )
        second = await get_or_create_account(
            session, code=code, type=LedgerAccountType.ASSET, currency="EUR", description="d"
        )
        await commit(session)
    assert first == second


async def test_balances_view_refresh(sessionmaker: SM) -> None:
    clearing, seller = await _accounts(sessionmaker)
    await _post(
        sessionmaker,
        f"mv:{new_id()}",
        [EntryInput(clearing, "D", _eur(700)), EntryInput(seller, "C", _eur(700))],
    )
    async with sessionmaker() as session:
        await session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY ledger_balances"))
        await session.commit()
        balance = await session.scalar(
            text("SELECT debit_balance_minor FROM ledger_balances WHERE account_id = :a"),
            {"a": clearing},
        )
    assert balance == 700


# --- Property tests (hypothesis) -----------------------------------------------------------

CURRENCIES = ("EUR", "PLN", "SEK")
PROPERTY_SETTINGS = settings(
    max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)


@st.composite
def balanced_sets(draw: st.DrawFn) -> list[tuple[str, int, str]]:
    """1 to 3 currencies; per currency, debits and credits with equal totals."""
    currencies = draw(st.lists(st.sampled_from(CURRENCIES), min_size=1, max_size=3, unique=True))
    entries: list[tuple[str, int, str]] = []
    for currency in currencies:
        debits = draw(st.lists(st.integers(1, 10**9), min_size=1, max_size=4))
        total = sum(debits)
        cuts = (
            sorted(draw(st.sets(st.integers(1, total - 1), max_size=min(3, total - 1))))
            if total > 1
            else []
        )
        bounds = [0, *cuts, total]
        credit_amounts = [b - a for a, b in itertools.pairwise(bounds)]
        entries += [(currency, amount, "D") for amount in debits]
        entries += [(currency, amount, "C") for amount in credit_amounts]
    return draw(st.permutations(entries))


async def _accounts_by_currency(sm: SM) -> dict[str, tuple[UUID, UUID]]:
    return {currency: await _accounts(sm, currency) for currency in CURRENCIES}


async def _post_raw(
    sm: SM, rows: list[tuple[str, int, str]], accounts: dict[str, tuple[UUID, UUID]]
) -> None:
    async with sm() as session:
        transaction_id = await _raw_transaction(session)
        for currency, amount, direction in rows:
            debit_account, credit_account = accounts[currency]
            account = debit_account if direction == "D" else credit_account
            await _raw_entry(session, transaction_id, account, direction, amount, currency)
        await session.commit()


@PROPERTY_SETTINGS
@given(rows=balanced_sets())
def test_property_random_balanced_sets_commit(
    loop_thread: LoopThread, rows: list[tuple[str, int, str]]
) -> None:
    accounts = loop_thread.run(_accounts_by_currency(loop_thread.sessionmaker))
    loop_thread.run(_post_raw(loop_thread.sessionmaker, rows, accounts))


@PROPERTY_SETTINGS
@given(rows=balanced_sets(), delta=st.integers(1, 10**6), index=st.integers(0))
def test_property_random_unbalanced_sets_rejected(
    loop_thread: LoopThread, rows: list[tuple[str, int, str]], delta: int, index: int
) -> None:
    currency, amount, direction = rows[index % len(rows)]
    rows = [*rows]
    rows[index % len(rows)] = (currency, amount + delta, direction)
    accounts = loop_thread.run(_accounts_by_currency(loop_thread.sessionmaker))
    with pytest.raises(DBAPIError, match="unbalanced"):
        loop_thread.run(_post_raw(loop_thread.sessionmaker, rows, accounts))


async def _sums_by_currency(sm: SM) -> dict[str, int]:
    async with sm() as session:
        rows = await session.execute(
            text(
                "SELECT currency, sum(CASE direction WHEN 'D' THEN amount_minor"
                " ELSE -amount_minor END) FROM ledger_entries GROUP BY currency"
            )
        )
        return {row[0]: int(row[1]) for row in rows}


def test_property_sum_of_all_balances_is_zero(loop_thread: LoopThread) -> None:
    """After every test above (hundreds of random transactions), each currency nets to zero."""
    sums = loop_thread.run(_sums_by_currency(loop_thread.sessionmaker))
    assert sums
    assert all(total == 0 for total in sums.values())


async def test_concurrent_posts_same_key_single_transaction(sessionmaker: SM) -> None:
    import asyncio

    clearing, seller = await _accounts(sessionmaker)
    key = f"concurrent:{new_id()}"
    reference = new_id()
    entries = [EntryInput(clearing, "D", _eur(500)), EntryInput(seller, "C", _eur(500))]
    results = await asyncio.gather(
        *(_post(sessionmaker, key, entries, reference) for _ in range(5))
    )
    assert len({transaction_id for transaction_id, _ in results}) == 1
    assert sorted(replayed for _, replayed in results) == [False, True, True, True, True]
    async with sessionmaker() as session:
        assert await account_balance(session, clearing, "EUR") == _eur(500)
