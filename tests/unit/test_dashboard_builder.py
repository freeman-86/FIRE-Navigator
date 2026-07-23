import unittest
from datetime import date

from core.domain.account import Account, AccountType
from core.domain.asset import Asset
from core.domain.expense import Expense
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from reports.dashboard_builder import (
    build_dashboard,
    compute_asset_depletion_age,
    compute_reverse_annual_budget,
)
from core.simulation.projection.projection_engine import run_projection
from tests.pension_test_fixtures import zero_pension_rules
from tests.portfolio_test_fixtures import empty_portfolio_rules, no_allocation_contribution_strategy
from tests.tax_test_fixtures import zero_tax_rules

BASE_EXPENSE = 1_000_000
INITIAL_BALANCE = 30_000_000


def _plan() -> Plan:
    user = User(birth_date=date(1990, 4, 1))
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )
    income = Income(
        income_id="income_001",
        source="salary",
        amount=Money.of(BASE_EXPENSE),
        growth_rate=Rate.zero(),
        start_condition=EventCondition.plan_start(),
    )
    expense = Expense(
        expense_id="expense_001",
        category="living",
        amount=Money.of(BASE_EXPENSE),
        growth_rate=Rate.zero(),
    )
    return Plan(
        plan_id="plan_test",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.zero()),
        accounts=[Account(account_id="acc_taxable", account_type=AccountType.TAXABLE)],
        tax_config=TaxConfig(),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.TAXABLE]),
        contribution_strategy=no_allocation_contribution_strategy(),
        incomes=[income],
        expenses=[expense],
    )


def _portfolios(balance: int = INITIAL_BALANCE) -> dict[str, Portfolio]:
    asset = Asset(asset_class="cash", expected_return=Rate.zero())
    holding = Holding(asset=asset, quantity=1, current_value=Money.of(balance), cost_basis=Money.of(balance))
    return {"acc_taxable": Portfolio(holdings=[holding])}


class ComputeAssetDepletionAgeTest(unittest.TestCase):
    def test_returns_none_when_never_depletes(self) -> None:
        plan = _plan()
        result = run_projection(plan, _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules())
        self.assertIsNone(compute_asset_depletion_age(result))

    def test_returns_age_of_first_depletion_year(self) -> None:
        plan = _plan()
        # 収支ゼロの生活費に加えて500万円/年の生活費超過分は口座残高100万円だとすぐ枯渇する
        plan.expenses.append(Expense(expense_id="extra", category="extra", amount=Money.of(5_000_000), growth_rate=Rate.zero()))
        result = run_projection(plan, _portfolios(1_000_000), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules())

        # start_condition=2026-01-01, birth_date=1990-04-01 -> 初年度(2026年)に年齢36歳で枯渇する
        self.assertEqual(compute_asset_depletion_age(result), 36)


class ComputeReverseAnnualBudgetTest(unittest.TestCase):
    def test_finds_budget_close_to_analytically_expected_value(self) -> None:
        plan = _plan()
        portfolios = _portfolios()
        # 成長率0%・基礎収支0のプランなので、年30年間X円ずつ追加で使うとending networth = INITIAL_BALANCE - 30*X
        target_extra = 300_000
        target_ending_networth = Money.of(INITIAL_BALANCE - 30 * target_extra)

        budget = compute_reverse_annual_budget(
            plan, portfolios, zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules(), target_ending_networth
        )

        self.assertAlmostEqual(int(budget.amount), target_extra, delta=5_000)

    def test_returns_zero_when_target_exceeds_baseline(self) -> None:
        plan = _plan()
        portfolios = _portfolios()
        unreachable_target = Money.of(1_000_000_000)

        budget = compute_reverse_annual_budget(
            plan, portfolios, zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules(), unreachable_target
        )

        self.assertEqual(budget, Money.zero())

    def test_returns_upper_bound_when_target_is_very_low(self) -> None:
        plan = _plan()
        portfolios = _portfolios()
        # ending_networth(extra) = 30,000,000 - 30*extra（成長率0%・線形）なので、
        # extra=上限(1億円)でも -2,970,000,000 円。それを下回るtargetを設定して上限到達を確認する。
        very_low_target = Money.of(-3_000_000_000)

        budget = compute_reverse_annual_budget(
            plan, portfolios, zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules(), very_low_target
        )

        self.assertEqual(budget.amount, 100_000_000)


class BuildDashboardTest(unittest.TestCase):
    def test_assembles_all_expected_fields(self) -> None:
        plan = _plan()
        portfolios = _portfolios()

        dashboard = build_dashboard(
            plan, portfolios, zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules(), Money.zero()
        )

        self.assertEqual(dashboard["current_networth"], Money.of(INITIAL_BALANCE))
        self.assertEqual(
            dashboard["extra_monthly_budget"], Money.of(dashboard["extra_annual_budget"].amount / 12)
        )
        self.assertIsNone(dashboard["depletion_age"])
        self.assertEqual(dashboard["target_ending_networth"], Money.zero())


if __name__ == "__main__":
    unittest.main()
