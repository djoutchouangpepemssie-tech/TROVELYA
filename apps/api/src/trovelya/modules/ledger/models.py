"""Ledger value types."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from trovelya.shared.money import Money

Direction = Literal["D", "C"]


class LedgerAccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    REVENUE = "revenue"
    EXPENSE = "expense"
    EQUITY = "equity"


@dataclass(frozen=True, slots=True)
class EntryInput:
    account_id: UUID
    direction: Direction
    amount: Money

    def __post_init__(self) -> None:
        if self.direction not in ("D", "C"):
            raise ValueError("direction must be 'D' or 'C'")
        if self.amount.amount_minor <= 0:
            raise ValueError("ledger entry amount must be positive")


@dataclass(frozen=True, slots=True)
class PostedTransaction:
    id: UUID
    replayed: bool
