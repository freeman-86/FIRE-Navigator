from datetime import date

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.expense import Expense
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy

CONFIG_VERSION_LABEL = "sprint10-spouse-deduction"


def build_plan() -> Plan:
    """回帰テスト用の固定シナリオ（配偶者控除あり、退職マイルストーンなし）。
    この関数の内容を変更するとgolden fileとの比較が意図的に崩れるため、
    変更する場合はtests/regression/golden/を再生成しレビューを経ること。
    """

    spouse = User(birth_date=date(1992, 6, 1), residence=Prefecture.TOKYO)
    user = User(birth_date=date(1988, 3, 1), residence=Prefecture.TOKYO, spouse=spouse)

    account = Account(account_id="acc_taxable_001", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)

    income = Income(
        income_id="income_salary_001",
        source="salary",
        amount=Money.of(7_000_000),
        growth_rate=Rate.from_percent(1),
        start_condition=EventCondition.plan_start(),
    )
    expense = Expense(
        expense_id="expense_living_001",
        category="living",
        amount=Money.of(4_000_000),
        growth_rate=Rate.from_percent(2),
        is_flexible=False,
    )
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )

    return Plan(
        plan_id="plan_regression_spouse_deduction",
        name="回帰テスト用プラン（配偶者控除あり）",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.from_percent(2), investment_growth_rate=Rate.from_percent(4)),
        accounts=[account],
        tax_config=TaxConfig(residence=Prefecture.TOKYO, deduction_settings={"spouse_deduction": True}),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH, AccountType.TAXABLE]),
        contribution_strategy=ContributionStrategy(order=[AccountType.TAXABLE]),
        incomes=[income],
        expenses=[expense],
    )


def build_portfolios() -> dict[str, Portfolio]:
    asset = Asset(
        asset_class="equity_sp500", expected_return=Rate.from_percent(5), volatility=Rate.from_percent(15)
    )
    holding = Holding(asset=asset, quantity=1, cost_basis=Money.of(2_000_000))
    return {"acc_taxable_001": Portfolio(holdings=[holding])}
