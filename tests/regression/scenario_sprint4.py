from datetime import date
from typing import Optional

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset, AssetClass
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.expense import Expense
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.milestone import Milestone, MilestoneType
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy

CONFIG_VERSION_LABEL = "sprint7-baseline"

_ACCOUNT_SPECS: tuple[tuple[str, AccountType, int, AssetClass, Optional[int]], ...] = (
    ("acc_cash_001", AccountType.CASH, 1_000_000, "cash", None),
    ("acc_nisa_growth_001", AccountType.NISA_GROWTH, 3_000_000, "equity_sp500", 50_000),
    ("acc_ideco_001", AccountType.IDECO, 1_500_000, "bond_us_treasury", 23_000),
    ("acc_taxable_001", AccountType.TAXABLE, 500_000, "equity_sp500", None),
)


def build_scenario_plan() -> Plan:
    """回帰テスト用の固定シナリオ。この関数の内容を変更すると golden file との比較が意図的に崩れるため、
    変更する場合は tests/regression/golden/ を再生成しレビューを経ること。
    """

    user = User(birth_date=date(1990, 4, 1), residence=Prefecture.TOKYO)

    accounts = [
        Account(
            account_id=account_id,
            account_type=account_type,
            owner=OwnerType.SELF,
            monthly_contribution=Money.of(monthly_contribution) if monthly_contribution is not None else None,
        )
        for account_id, account_type, _balance, _asset_class, monthly_contribution in _ACCOUNT_SPECS
    ]

    incomes = [
        Income(
            income_id="income_salary_001",
            source="salary",
            amount=Money.of(6_000_000),
            growth_rate=Rate.from_percent(1),
            start_condition=EventCondition.plan_start(),
            end_condition=EventCondition.at_age(60),
        )
    ]

    expenses = [
        Expense(
            expense_id="expense_living_001",
            category="living",
            amount=Money.of(3_600_000),
            growth_rate=Rate.from_percent(2),
            is_flexible=False,
        )
    ]

    milestones = [
        Milestone(
            milestone_id="milestone_retire_001",
            milestone_type=MilestoneType.RETIREMENT,
            trigger=EventCondition.at_age(65),
        )
    ]

    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.of(780_000)),
        employee_pension=PensionEntitlement(estimate_annual=Money.of(1_200_000)),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )

    return Plan(
        plan_id="plan_regression_sprint4",
        name="回帰テスト用ベースプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.from_percent(2), investment_growth_rate=Rate.from_percent(5)),
        accounts=accounts,
        tax_config=TaxConfig(residence=Prefecture.TOKYO),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(
            order=[AccountType.CASH, AccountType.TAXABLE, AccountType.NISA_GROWTH, AccountType.IDECO]
        ),
        contribution_strategy=ContributionStrategy(
            order=[AccountType.CASH, AccountType.NISA_GROWTH, AccountType.IDECO, AccountType.TAXABLE],
            emergency_fund_target=Money.of(1_500_000),
        ),
        milestones=milestones,
        incomes=incomes,
        expenses=expenses,
    )


def build_scenario_portfolios() -> dict[str, Portfolio]:
    """固定シナリオのPortfolio Aggregate（account_idで参照する独立集約）。"""

    portfolios = {}
    for account_id, _account_type, balance, asset_class, _monthly_contribution in _ACCOUNT_SPECS:
        asset = Asset(asset_class=asset_class, expected_return=Rate.from_percent(5), volatility=Rate.from_percent(15))
        portfolios[account_id] = Portfolio(holdings=[Holding(asset=asset, quantity=1, current_value=Money.of(balance), cost_basis=Money.of(balance))])
    return portfolios
