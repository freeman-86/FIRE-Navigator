import unittest
from datetime import date

from core.domain.account import Account, AccountType
from core.domain.asset import Asset
from core.domain.errors import SemanticValidationError
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.montecarlo_result import MonteCarloResult, PercentileBand
from core.domain.pension import ClaimTiming, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.services.pipeline_service import PipelineOutcome, run_pipeline_for_plan
from reports.output_builder import OUTPUT_SCHEMA_VERSION, build_output_json
from tests.portfolio_test_fixtures import no_allocation_contribution_strategy


def _plan_and_portfolios() -> tuple[Plan, dict[str, Portfolio]]:
    user = User(birth_date=date(1990, 4, 1))
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(age=65),
    )
    plan = Plan(
        plan_id="plan_test",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.zero()),
        accounts=[Account(account_id="acc_1", account_type=AccountType.TAXABLE)],
        tax_config=TaxConfig(),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH, AccountType.TAXABLE]),
        contribution_strategy=no_allocation_contribution_strategy(),
        incomes=[
            Income(
                income_id="income_1",
                source="salary",
                amount=Money.of(3_000_000),
                growth_rate=Rate.zero(),
                start_condition=EventCondition.plan_start(),
            )
        ],
    )
    asset = Asset(asset_class="equity_sp500", expected_return=Rate.zero())
    holding = Holding(asset=asset, quantity=1, current_value=Money.of(1_000_000), cost_basis=Money.of(1_000_000))
    portfolios = {"acc_1": Portfolio(holdings=[holding])}
    return plan, portfolios


class BuildOutputJsonSuccessTest(unittest.TestCase):
    def setUp(self) -> None:
        plan, portfolios = _plan_and_portfolios()
        self.outcome = run_pipeline_for_plan(
            plan, portfolios, Money.of(5_000_000), skip_montecarlo=True, skip_historical=True
        )
        self.output = build_output_json(self.outcome)

    def test_top_level_shape(self) -> None:
        self.assertEqual(self.output["plan_id"], "plan_test")
        self.assertEqual(self.output["schema_version"], OUTPUT_SCHEMA_VERSION)
        self.assertEqual(self.output["errors"], [])
        self.assertEqual(self.output["warnings"], [])

    def test_dashboard_is_json_safe_plain_types(self) -> None:
        dashboard = self.output["dashboard"]
        self.assertIsInstance(dashboard["current_networth"], int)
        self.assertIsInstance(dashboard["target_ending_networth"], int)
        self.assertEqual(dashboard["target_ending_networth"], 5_000_000)
        for entry in dashboard["asset_allocation"]:
            self.assertIsInstance(entry["amount"], int)
            self.assertIsInstance(entry["weight"], float)

    def test_networth_chart_is_populated(self) -> None:
        chart = self.output["charts"]["networth_chart"]
        self.assertEqual(chart["type"], "stacked_area")
        self.assertTrue(len(chart["x"]) > 0)

    def test_montecarlo_charts_are_none_when_skipped(self) -> None:
        self.assertIsNone(self.output["charts"]["montecarlo_distribution_chart"])
        self.assertIsNone(self.output["charts"]["historical_distribution_chart"])
        self.assertIsNone(self.output["summary"]["montecarlo_success_rate"])
        self.assertIsNone(self.output["summary"]["historical_success_rate"])

    def test_sensitivity_table_is_populated(self) -> None:
        table = self.output["tables"]["sensitivity_table"]
        self.assertEqual(table["type"], "grid")
        self.assertTrue(len(table["row_labels"]) > 0)

    def test_monthly_detail_is_populated_and_json_safe(self) -> None:
        monthly = self.output["tables"]["monthly_detail"]
        self.assertEqual(monthly["columns"][:3], ["year", "month", "age"])
        self.assertEqual(monthly["column_labels"][:3], ["西暦年", "月", "年齢"])
        self.assertTrue(len(monthly["rows"]) > 0)
        first_row = monthly["rows"][0]
        self.assertEqual(len(first_row), len(monthly["columns"]))
        for value in first_row:
            self.assertIsInstance(value, int)

    def test_does_not_include_raw_dataclasses(self) -> None:
        # simulation_result/montecarlo_result（生の年次・試行ごとのデータ）はJSON化できないため含めない
        self.assertNotIn("simulation_result", self.output)
        self.assertNotIn("montecarlo_result", self.output)


class BuildOutputJsonMontecarloReference1971Test(unittest.TestCase):
    def test_reference_1971_chart_is_populated_when_present(self) -> None:
        plan, _ = _plan_and_portfolios()
        reference_result = MonteCarloResult(
            trials=10,
            success_count=10,
            success_rate=1.0,
            percentile_networth_by_year={
                2026: PercentileBand(p10=Money.of(1_000_000), p50=Money.of(2_000_000), p90=Money.of(3_000_000)),
            },
        )
        outcome = PipelineOutcome(plan=plan, montecarlo_reference_1971_result=reference_result)

        output = build_output_json(outcome)

        chart = output["diagnostics"]["montecarlo_reference_1971_chart"]
        self.assertIsNotNone(chart)
        self.assertEqual(chart["type"], "percentile_band")
        self.assertEqual(chart["x"], [2026])
        self.assertEqual(chart["p50"], [2_000_000])

    def test_reference_1971_chart_is_none_when_absent(self) -> None:
        plan, _ = _plan_and_portfolios()
        outcome = PipelineOutcome(plan=plan)

        output = build_output_json(outcome)

        self.assertIsNone(output["diagnostics"]["montecarlo_reference_1971_chart"])


class BuildOutputJsonFailureTest(unittest.TestCase):
    def test_semantic_errors_are_surfaced_and_other_fields_stay_empty(self) -> None:
        plan, _ = _plan_and_portfolios()
        # run_pipeline_for_plan()が意味的エラーで打ち切った場合と同じ形（plan以外は未計算のまま）
        outcome = PipelineOutcome(plan=plan, semantic_errors=[SemanticValidationError("テストエラー", "some.field")])

        output = build_output_json(outcome)

        self.assertEqual(output["errors"], [{"field_path": "some.field", "message": "テストエラー"}])
        self.assertIsNone(output["dashboard"])
        self.assertIsNone(output["tables"]["sensitivity_table"])
        self.assertIsNone(output["tables"]["monthly_detail"])
        self.assertIsNone(output["charts"]["networth_chart"])


if __name__ == "__main__":
    unittest.main()
