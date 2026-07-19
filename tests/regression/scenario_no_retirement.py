from datetime import date

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset, AssetClass
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

CONFIG_VERSION_LABEL = "sprint10-no-retirement"


def build_plan() -> Plan:
    """回帰テスト用の固定シナリオ（退職マイルストーンなし＝通常30年ホライズン、NISA/iDeCo拠出あり）。
    この関数の内容を変更するとgolden fileとの比較が意図的に崩れるため、
    変更する場合はtests/regression/golden/を再生成しレビューを経ること。
    """

    user = User(birth_date=date(1995, 1, 1), residence=Prefecture.OSAKA)

    accounts = [
        Account(account_id="acc_cash_001", account_type=AccountType.CASH, owner=OwnerType.SELF),
        Account(
            account_id="acc_nisa_growth_001",
            account_type=AccountType.NISA_GROWTH,
            owner=OwnerType.SELF,
            monthly_contribution=Money.of(80_000),
        ),
        Account(
            account_id="acc_ideco_001",
            account_type=AccountType.IDECO,
            owner=OwnerType.SELF,
            monthly_contribution=Money.of(23_000),
        ),
    ]

    income = Income(
        income_id="income_salary_001",
        source="salary",
        amount=Money.of(5_500_000),
        growth_rate=Rate.from_percent(2),
        start_condition=EventCondition.plan_start(),
    )
    expense = Expense(
        expense_id="expense_living_001",
        category="living",
        amount=Money.of(3_000_000),
        growth_rate=Rate.from_percent(1.5),
        is_flexible=False,
    )
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )

    return Plan(
        plan_id="plan_regression_no_retirement",
        name="回帰テスト用プラン（退職マイルストーンなし）",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.from_percent(2), investment_growth_rate=Rate.from_percent(6)),
        accounts=accounts,
        tax_config=TaxConfig(residence=Prefecture.OSAKA),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH, AccountType.TAXABLE]),
        contribution_strategy=ContributionStrategy(
            order=[AccountType.CASH, AccountType.NISA_GROWTH, AccountType.IDECO, AccountType.TAXABLE],
            emergency_fund_target=Money.of(2_000_000),
        ),
        incomes=[income],
        expenses=[expense],
    )


def build_portfolios() -> dict[str, Portfolio]:
    def _portfolio(balance: int, asset_class: AssetClass) -> Portfolio:
        asset = Asset(asset_class=asset_class, expected_return=Rate.from_percent(5), volatility=Rate.from_percent(15))
        return Portfolio(holdings=[Holding(asset=asset, quantity=1, cost_basis=Money.of(balance))])

    return {
        "acc_cash_001": _portfolio(1_500_000, "cash"),
        "acc_nisa_growth_001": _portfolio(500_000, "equity_sp500"),
        "acc_ideco_001": _portfolio(300_000, "bond_us_treasury"),
    }
