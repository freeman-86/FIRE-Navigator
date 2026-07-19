from datetime import date

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.expense import Expense
from core.domain.holding import Holding
from core.domain.milestone import Milestone, MilestoneType
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy

CONFIG_VERSION_LABEL = "sprint10-account-exhaustion"


def build_plan() -> Plan:
    """回帰テスト用の固定シナリオ（口座枯渇ケース）。収入なし・資産少・支出大で、
    Withdrawal Engineが全口座を使い切りunallocated_surplusがマイナスになる経路を検証する。
    この関数の内容を変更するとgolden fileとの比較が意図的に崩れるため、
    変更する場合はtests/regression/golden/を再生成しレビューを経ること。
    """

    user = User(birth_date=date(1960, 1, 1), residence=Prefecture.TOKYO)

    account = Account(account_id="acc_taxable_001", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)

    expense = Expense(
        expense_id="expense_living_001",
        category="living",
        amount=Money.of(4_000_000),
        growth_rate=Rate.from_percent(2),
        is_flexible=False,
    )
    milestone = Milestone(
        milestone_id="milestone_retire_001",
        milestone_type=MilestoneType.RETIREMENT,
        trigger=EventCondition.at_age(66),
    )
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.of(700_000)),
        employee_pension=PensionEntitlement(estimate_annual=Money.of(300_000)),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )

    return Plan(
        plan_id="plan_regression_account_exhaustion",
        name="回帰テスト用プラン（口座枯渇ケース）",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.from_percent(2), investment_growth_rate=Rate.from_percent(3)),
        accounts=[account],
        tax_config=TaxConfig(residence=Prefecture.TOKYO),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.TAXABLE]),
        contribution_strategy=ContributionStrategy(order=[AccountType.TAXABLE]),
        expenses=[expense],
        milestones=[milestone],
    )


def build_portfolios() -> dict[str, Portfolio]:
    asset = Asset(
        asset_class="bond_us_treasury", expected_return=Rate.from_percent(3), volatility=Rate.from_percent(5)
    )
    holding = Holding(asset=asset, quantity=1, current_value=Money.of(3_000_000), cost_basis=Money.of(3_000_000))
    return {"acc_taxable_001": Portfolio(holdings=[holding])}
