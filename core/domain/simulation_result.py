from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.domain.value_objects import Money, Rate


@dataclass
class YearlyProjection:
    year: int
    age_self: int
    gross_income: Money
    pension_income: Money
    income_tax: Money
    resident_tax: Money
    social_insurance: Money
    net_income: Money
    total_expense: Money
    net_cashflow: Money
    account_balances: dict[str, Money]
    networth: Money


@dataclass
class MonthlyProjection:
    """年末時点の集計であるYearlyProjectionとは別に、月次の資金の動き（FIRE後の毎月の取り崩し等）を
    追跡するための明細（Sprint12 月次化）。gross_income/pension_income/net_income/total_expenseは
    年額を12等分した値（税額は年1回の確定計算をそのまま月割りする簡略化。設計書v1.1採用ロードマップ）。
    """

    year: int
    month: int
    age_self: int
    gross_income: Money
    pension_income: Money
    net_income: Money
    total_expense: Money
    net_cashflow: Money
    account_balances: dict[str, Money]
    networth: Money


@dataclass
class TaxAnalyticsEntry:
    marginal_rate: Rate
    effective_rate: Rate


@dataclass
class MilestoneOutcome:
    milestone_id: str
    achieved: bool
    achieved_year: Optional[int] = None


@dataclass
class SimulationResult:
    yearly_projections: list[YearlyProjection] = field(default_factory=list)
    monthly_projections: list[MonthlyProjection] = field(default_factory=list)
    tax_analytics: dict[int, TaxAnalyticsEntry] = field(default_factory=dict)
    milestone_outcomes: list[MilestoneOutcome] = field(default_factory=list)
