from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.value_objects import Money, Rate


@dataclass
class RepaymentEntry:
    year: int
    principal_payment: Money
    interest_payment: Money
    remaining_balance: Money


@dataclass
class RepaymentSchedule:
    entries: list[RepaymentEntry] = field(default_factory=list)


@dataclass
class Loan:
    loan_id: str
    principal: Money
    interest_rate: Rate
    term_years: int
    repayment_schedule: RepaymentSchedule = field(default_factory=RepaymentSchedule)

    def __post_init__(self) -> None:
        if self.principal.is_negative:
            raise ValueError("principal は負の値にできません")
        if self.term_years <= 0:
            raise ValueError("term_years は正の値である必要があります")
