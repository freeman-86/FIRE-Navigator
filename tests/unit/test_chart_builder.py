import unittest
from datetime import date

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset, AssetClass
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.simulation.projection.projection_engine import run_projection
from reports.chart_builder import build_networth_chart
from reports.output_builder import OUTPUT_SCHEMA_VERSION, build_output_json
from tests.tax_test_fixtures import zero_tax_rules


def _plan_with_two_account_types() -> Plan:
    user = User(birth_date=date(1990, 4, 1), residence=Prefecture.TOKYO)

    def _account(account_id: str, account_type: AccountType, balance: int) -> Account:
        asset = Asset(
            asset_class=AssetClass.GLOBAL_EQUITY,
            expected_return=Rate.from_percent(5),
            volatility=Rate.from_percent(15),
        )
        holding = Holding(asset=asset, quantity=1, cost_basis=Money.of(balance))
        return Account(
            account_id=account_id,
            account_type=account_type,
            owner=OwnerType.SELF,
            portfolio=Portfolio(holdings=[holding]),
        )

    income = Income(
        income_id="income_001",
        source="salary",
        amount=Money.of(1_000_000),
        growth_rate=Rate.zero(),
        start_condition=EventCondition.plan_start(),
    )

    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )

    return Plan(
        plan_id="plan_test",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.from_percent(5)),
        accounts=[
            _account("acc_taxable_001", AccountType.TAXABLE, 1_000_000),
            _account("acc_nisa_001", AccountType.NISA_GROWTH, 500_000),
        ],
        tax_config=TaxConfig(residence=Prefecture.TOKYO),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
        incomes=[income],
    )


class ChartBuilderTest(unittest.TestCase):
    def test_series_grouped_by_account_type_plus_unallocated_surplus(self) -> None:
        plan = _plan_with_two_account_types()
        result = run_projection(plan, zero_tax_rules())

        chart = build_networth_chart(plan, result)

        self.assertEqual(chart["type"], "stacked_area")
        series_names = {series["name"] for series in chart["series"]}
        self.assertEqual(series_names, {"taxable", "nisa_growth", "unallocated_surplus"})

        first_year_totals = {series["name"]: series["values"][0] for series in chart["series"]}
        self.assertEqual(first_year_totals["taxable"], 1_050_000)
        self.assertEqual(first_year_totals["nisa_growth"], 525_000)
        self.assertEqual(first_year_totals["unallocated_surplus"], 1_000_000)

    def test_series_values_sum_to_networth(self) -> None:
        plan = _plan_with_two_account_types()
        result = run_projection(plan, zero_tax_rules())
        chart = build_networth_chart(plan, result)

        for index, projection in enumerate(result.yearly_projections):
            total = sum(series["values"][index] for series in chart["series"])
            self.assertEqual(total, int(projection.networth.amount))


class OutputBuilderTest(unittest.TestCase):
    def test_output_json_introduces_charts_field_with_other_fields_empty(self) -> None:
        plan = _plan_with_two_account_types()
        result = run_projection(plan, zero_tax_rules())

        output = build_output_json(plan, result)

        self.assertEqual(output["plan_id"], "plan_test")
        self.assertEqual(output["schema_version"], OUTPUT_SCHEMA_VERSION)
        self.assertIn("networth_chart", output["charts"])
        self.assertEqual(output["summary"], {})
        self.assertEqual(output["metrics"], {})
        self.assertEqual(output["tables"], {})
        self.assertEqual(output["diagnostics"], {})
        self.assertIsNone(output["montecarlo_result"])
        self.assertEqual(output["warnings"], [])
        self.assertEqual(output["errors"], [])
        self.assertIs(output["simulation_result"], result)


if __name__ == "__main__":
    unittest.main()
