"""Ledger errors."""


class LedgerError(Exception):
    pass


class LedgerUnbalancedError(LedgerError):
    """Debits and credits differ for at least one currency."""


class LedgerCurrencyMismatchError(LedgerError):
    """An entry's currency is not its account's currency."""


class LedgerIdempotencyConflictError(LedgerError):
    """The idempotency key was already used for a different transaction."""
