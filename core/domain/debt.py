from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.domain.value_objects import Money, Rate


class DebtType(str, Enum):
    STUDENT_LOAN = "student_loan"
    CREDIT_CARD = "credit_card"
    AUTO_LOAN = "auto_loan"
    OTHER = "other"


@dataclass
class Debt:
    debt_id: str
    debt_type: DebtType
    balance: Money
    interest_rate: Rate

    def __post_init__(self) -> None:
        if self.balance.is_negative:
            raise ValueError("balance は負の値にできません")
