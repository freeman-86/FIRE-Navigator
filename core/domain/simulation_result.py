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
    capital_gains_tax: Money = field(default_factory=Money.zero)


@dataclass
class MonthlyProjection:
    """年末時点の集計であるYearlyProjectionとは別に、月次の資金の動き（FIRE後の毎月の取り崩し等）を
    追跡するための明細（Sprint12 月次化）。gross_income/pension_income/total_expenseはその月ちょうどの
    実額（収入・支出の開始/終了条件、年金受給資格をその月単位で判定した値）。net_incomeもこれらの
    実額から算出するが、所得税・住民税・社会保険料の3税だけは年1回の確定計算をそのまま月割りする
    （日本の税制がそもそも年次確定であるため。設計書v1.1採用ロードマップ）。
    capital_gains_taxは課税口座からの取り崩し時に発生した譲渡税（Sprint13 譲渡税・取得原価管理）。
    remaining_shortfallは口座残高を取り崩してもなお賄いきれなかった不足額（withdraw_shortfallの
    戻り値をそのまま転記。口座を強制的に取り崩すことはしないため、資産が尽きた月はここに残る）。
    net_cashflowがマイナスでも口座から取り崩せていれば0円（FIRE後の取り崩しは正常な状態のため）。
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
    capital_gains_tax: Money = field(default_factory=Money.zero)
    withdrawals_by_asset_class: dict[str, Money] = field(default_factory=dict)
    remaining_shortfall: Money = field(default_factory=Money.zero)


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
