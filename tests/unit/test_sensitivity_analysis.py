import unittest
from datetime import date

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.simulation.projection.sensitivity_analysis import run_sensitivity_analysis
from reports.sensitivity_analysis_builder import build_sensitivity_table
from tests.pension_test_fixtures import zero_pension_rules
from tests.portfolio_test_fixtures import empty_portfolio_rules, no_allocation_contribution_strategy
from tests.tax_test_fixtures import zero_tax_rules


def _plan() -> Plan:
    user = User(birth_date=date(1990, 4, 1), residence=Prefecture.TOKYO)
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )
    income = Income(
        income_id="income_001",
        source="salary",
        amount=Money.of(5_000_000),
        growth_rate=Rate.zero(),
        start_condition=EventCondition.plan_start(),
    )
    return Plan(
        plan_id="plan_test",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.from_percent(2), investment_growth_rate=Rate.from_percent(5)),
        accounts=[Account(account_id="acc_001", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)],
        tax_config=TaxConfig(residence=Prefecture.TOKYO),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
        contribution_strategy=no_allocation_contribution_strategy(),
        incomes=[income],
    )


def _portfolios() -> dict[str, Portfolio]:
    asset = Asset(asset_class="equity_sp500", expected_return=Rate.from_percent(5), volatility=Rate.from_percent(15))
    holding = Holding(asset=asset, quantity=1, current_value=Money.of(1_000_000), cost_basis=Money.of(1_000_000))
    return {"acc_001": Portfolio(holdings=[holding])}


class RunSensitivityAnalysisTest(unittest.TestCase):
    def test_returns_full_grid_of_growth_x_inflation_variations(self) -> None:
        result = run_sensitivity_analysis(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules()
        )

        self.assertEqual(len(result.growth_rate_labels), 3)
        self.assertEqual(len(result.inflation_rate_labels), 3)
        self.assertEqual(len(result.final_networth_grid), 9)

    def test_higher_growth_rate_produces_higher_final_networth(self) -> None:
        result = run_sensitivity_analysis(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules()
        )

        pessimistic = result.final_networth_grid[("-1%", "±0%")]
        base = result.final_networth_grid[("±0%", "±0%")]
        optimistic = result.final_networth_grid[("+1%", "±0%")]
        self.assertLess(pessimistic, base)
        self.assertLess(base, optimistic)

    def test_inflation_variation_is_included_in_grid_axis(self) -> None:
        # 現時点ではInflation_rateはIncome/Expenseの計算に反映されない(Income/Expenseは個別のgrowth_rateを持つ)ため、
        # 感応度分析としては成長率のみが結果に影響する。インフレ率の軸自体はグリッドに含まれることのみを確認する。
        result = run_sensitivity_analysis(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules()
        )

        self.assertEqual(result.inflation_rate_labels, ["-0.5%", "±0%", "+0.5%"])
        low_inflation = result.final_networth_grid[("±0%", "-0.5%")]
        high_inflation = result.final_networth_grid[("±0%", "+0.5%")]
        self.assertEqual(low_inflation, high_inflation)

    def test_base_plan_assumptions_are_not_mutated(self) -> None:
        plan = _plan()
        original_growth_rate = plan.assumptions.investment_growth_rate
        run_sensitivity_analysis(plan, _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules())
        self.assertEqual(plan.assumptions.investment_growth_rate, original_growth_rate)


class BuildSensitivityTableTest(unittest.TestCase):
    def test_table_shape_matches_grid(self) -> None:
        result = run_sensitivity_analysis(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules()
        )

        table = build_sensitivity_table(result)

        self.assertEqual(table["row_labels"], result.growth_rate_labels)
        self.assertEqual(table["column_labels"], result.inflation_rate_labels)
        self.assertEqual(len(table["cells"]), 3)
        self.assertEqual(len(table["cells"][0]), 3)
        self.assertEqual(
            table["cells"][0][0], int(result.final_networth_grid[(result.growth_rate_labels[0], result.inflation_rate_labels[0])].amount)
        )


if __name__ == "__main__":
    unittest.main()
