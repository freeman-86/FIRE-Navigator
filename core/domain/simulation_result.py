from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.domain.value_objects import Money, Rate


@dataclass
class YearlyProjection:
    year: int
    age_self: int
    gross_income: Money
    income_tax: Money
    resident_tax: Money
    social_insurance: Money
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
    tax_analytics: dict[int, TaxAnalyticsEntry] = field(default_factory=dict)
    milestone_outcomes: list[MilestoneOutcome] = field(default_factory=list)
