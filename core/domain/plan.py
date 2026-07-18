from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from core.domain.account import Account
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.debt import Debt
from core.domain.expense import Expense
from core.domain.income import Income
from core.domain.loan import Loan
from core.domain.milestone import Milestone
from core.domain.pension import Pension
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy


class StartConditionType(str, Enum):
    TODAY = "today"
    FIXED_DATE = "fixed_date"


@dataclass
class StartCondition:
    condition_type: StartConditionType
    fixed_date: Optional[date] = None

    def __post_init__(self) -> None:
        if self.condition_type == StartConditionType.FIXED_DATE and self.fixed_date is None:
            raise ValueError("condition_type='fixed_date' には fixed_date が必須です")


@dataclass
class Assumptions:
    inflation_rate: Rate
    investment_growth_rate: Rate
    config_ref: dict[str, str] = field(default_factory=dict)


@dataclass
class Plan:
    plan_id: str
    name: str
    user: User
    start_condition: StartCondition
    assumptions: Assumptions
    accounts: list[Account]
    tax_config: TaxConfig
    pension: Pension
    withdrawal_strategy: WithdrawalStrategy
    contribution_strategy: ContributionStrategy
    milestones: list[Milestone] = field(default_factory=list)
    debts: list[Debt] = field(default_factory=list)
    loans: list[Loan] = field(default_factory=list)
    incomes: list[Income] = field(default_factory=list)
    expenses: list[Expense] = field(default_factory=list)
