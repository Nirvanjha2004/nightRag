"""A simple bank account with an opening-balance floor, optional overdraft,
and a per-incident overdraft fee. Pure in-memory, no persistence.
"""

import datetime
from typing import Optional


class BankAccount:
    """Tracks an owner's balance and a list of every transaction.

    Withdrawals that exceed the current balance are only allowed when the
    account has overdraft enabled; otherwise they are rejected.
    """

    MIN_OPENING_BALANCE = 100.0
    OVERDRAFT_FEE = 25.0

    def __init__(self, owner: str, opening_balance: float = 0.0, overdraft: bool = False):
        if opening_balance < self.MIN_OPENING_BALANCE:
            raise ValueError(
                f"Opening balance must be at least {self.MIN_OPENING_BALANCE}"
            )
        self.owner = owner
        self.balance = opening_balance
        self.overdraft = overdraft
        self.transactions: list[dict] = []

    def _record(self, kind: str, amount: float) -> None:
        self.transactions.append(
            {
                "type": kind,
                "amount": amount,
                "ts": datetime.datetime.now().isoformat(),
            }
        )

    def deposit(self, amount: float) -> float:
        """Add money to the account and return the new balance."""
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        self.balance += amount
        self._record("deposit", amount)
        return self.balance

    def withdraw(self, amount: float) -> float:
        """Remove money. Rejected (ValueError) if it would overdraw and the
        account has overdraft disabled."""
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if amount > self.balance and not self.overdraft:
            raise ValueError("Insufficient funds — overdraft is disabled")
        self.balance -= amount
        self._record("withdraw", amount)
        return self.balance

    def apply_overdraft_fee(self) -> float:
        """If the balance is negative, charge OVERDRAFT_FEE and record it."""
        if self.balance < 0:
            self.balance -= self.OVERDRAFT_FEE
            self._record("overdraft_fee", self.OVERDRAFT_FEE)
        return self.balance

    def statement(self, limit: Optional[int] = None) -> list[dict]:
        """Most recent `limit` transactions (all of them if limit is None)."""
        if limit is None:
            return list(self.transactions)
        return self.transactions[-limit:]
