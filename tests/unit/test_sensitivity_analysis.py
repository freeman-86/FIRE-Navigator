import unittest
from datetime import date

from core.domain.account import Account, AccountType
from core.domain.asset import Asset
from core.domain.expense import Expense
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.pension import ClaimTiming, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.simulation.projection.sensitivity_analysis import run_sensitivity_analysis
from reports.sensitivity_analysis_builder import build_sensitivity_table
from tests.pension_test_fixtures import zero_pension_rules
from tests.portfolio_test_fixtures import empty_portfolio_rules, no_allocation_contribution_strategy
from tests.tax_test_fixtures import zero_tax_rules

_INFLATION_RATE = Rate.from_percent(2)


def _plan(*, expense_growth_rate_left_blank: bool = False) -> Plan:
    user = User(birth_date=date(1990, 4, 1))
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(age=65),
    )
    income = Income(
        income_id="income_001",
        source="salary",
        amount=Money.of(5_000_000),
        growth_rate=Rate.zero(),
        start_condition=EventCondition.plan_start(),
    )
    # 「成長率が空欄」だった行は、adapters/local/local_data_adapter._parse_growth_rateにより
    # 入力読込時点でinflation_rateと同じ値に解決されている前提を再現する。
    expense_growth_rate = _INFLATION_RATE if expense_growth_rate_left_blank else Rate.zero()
    expense = Expense(
        expense_id="expense_001",
        category="生活費",
        amount=Money.of(2_000_000),
        growth_rate=expense_growth_rate,
    )
    return Plan(
        plan_id="plan_test",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=_INFLATION_RATE),
        accounts=[Account(account_id="acc_001", account_type=AccountType.TAXABLE)],
        tax_config=TaxConfig(),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
        contribution_strategy=no_allocation_contribution_strategy(),
        incomes=[income],
        expenses=[expense],
    )


def _portfolios() -> dict[str, Portfolio]:
    asset = Asset(asset_class="equity_sp500", expected_return=Rate.from_percent(5))
    holding = Holding(asset=asset, quantity=1, current_value=Money.of(1_000_000), cost_basis=Money.of(1_000_000))
    return {"acc_001": Portfolio(holdings=[holding])}


class RunSensitivityAnalysisTest(unittest.TestCase):
    def test_returns_full_grid_of_expense_x_inflation_variations(self) -> None:
        result = run_sensitivity_analysis(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules()
        )

        self.assertEqual(len(result.expense_level_labels), 3)
        self.assertEqual(len(result.inflation_rate_labels), 3)
        self.assertEqual(len(result.final_networth_grid), 9)

    def test_higher_expense_level_produces_lower_final_networth(self) -> None:
        result = run_sensitivity_analysis(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules()
        )

        low_spending = result.final_networth_grid[("-10%", "±0%")]
        base = result.final_networth_grid[("±0%", "±0%")]
        high_spending = result.final_networth_grid[("+10%", "±0%")]
        self.assertGreater(low_spending, base)
        self.assertGreater(base, high_spending)

    def test_inflation_variation_changes_result_when_growth_rate_was_left_blank(self) -> None:
        # growth_rateが空欄だった行（inflation_rateと同値に解決済み）は、インフレ率を振ると
        # 新しいinflation_rateへ付け替わるため、結果が変わるはず（以前のバグの回帰防止）。
        plan = _plan(expense_growth_rate_left_blank=True)
        result = run_sensitivity_analysis(
            plan, _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules()
        )

        self.assertEqual(result.inflation_rate_labels, ["-0.5%", "±0%", "+0.5%"])
        low_inflation = result.final_networth_grid[("±0%", "-0.5%")]
        high_inflation = result.final_networth_grid[("±0%", "+0.5%")]
        self.assertNotEqual(low_inflation, high_inflation)

    def test_inflation_variation_does_not_affect_explicit_growth_rate(self) -> None:
        # growth_rateを明示的に指定していた行（たまたまinflation_rateと異なる値）は、
        # インフレ率を振っても変わらない。
        plan = _plan(expense_growth_rate_left_blank=False)
        result = run_sensitivity_analysis(
            plan, _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules()
        )

        low_inflation = result.final_networth_grid[("±0%", "-0.5%")]
        high_inflation = result.final_networth_grid[("±0%", "+0.5%")]
        self.assertEqual(low_inflation, high_inflation)

    def test_base_plan_and_portfolios_are_not_mutated(self) -> None:
        plan = _plan()
        portfolios = _portfolios()
        original_inflation_rate = plan.assumptions.inflation_rate
        original_expense_amount = plan.expenses[0].amount
        original_expected_return = portfolios["acc_001"].holdings[0].asset.expected_return

        run_sensitivity_analysis(plan, portfolios, zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules())

        self.assertEqual(plan.assumptions.inflation_rate, original_inflation_rate)
        self.assertEqual(plan.expenses[0].amount, original_expense_amount)
        self.assertEqual(portfolios["acc_001"].holdings[0].asset.expected_return, original_expected_return)


class BuildSensitivityTableTest(unittest.TestCase):
    def test_table_shape_matches_grid(self) -> None:
        result = run_sensitivity_analysis(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules()
        )

        table = build_sensitivity_table(result)

        self.assertEqual(table["row_labels"], result.expense_level_labels)
        self.assertEqual(table["column_labels"], result.inflation_rate_labels)
        self.assertEqual(len(table["cells"]), 3)
        self.assertEqual(len(table["cells"][0]), 3)
        self.assertEqual(
            table["cells"][0][0],
            int(
                result.final_networth_grid[
                    (result.expense_level_labels[0], result.inflation_rate_labels[0])
                ].amount
            ),
        )


if __name__ == "__main__":
    unittest.main()
