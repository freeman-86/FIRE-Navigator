import unittest
from datetime import date

from core.domain.account import Account, AccountType
from core.domain.asset import Asset
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.pension import ClaimTiming, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.simulation.projection.projection_engine import run_projection
from reports.chart_builder import build_networth_chart
from tests.pension_test_fixtures import zero_pension_rules
from tests.portfolio_test_fixtures import empty_portfolio_rules, no_allocation_contribution_strategy
from tests.tax_test_fixtures import zero_tax_rules


def _plan_with_two_account_types() -> tuple[Plan, dict[str, Portfolio]]:
    user = User(birth_date=date(1990, 4, 1))

    def _portfolio(balance: int) -> Portfolio:
        asset = Asset(
            asset_class="equity_sp500",
            expected_return=Rate.from_percent(5),
        )
        return Portfolio(holdings=[Holding(asset=asset, quantity=1, current_value=Money.of(balance), cost_basis=Money.of(balance))])

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
        claim_timing=ClaimTiming(age=65),
    )

    plan = Plan(
        plan_id="plan_test",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.zero()),
        accounts=[
            Account(account_id="acc_taxable_001", account_type=AccountType.TAXABLE),
            Account(account_id="acc_nisa_001", account_type=AccountType.NISA_GROWTH),
        ],
        tax_config=TaxConfig(),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
        contribution_strategy=no_allocation_contribution_strategy(),
        incomes=[income],
    )
    portfolios = {
        "acc_taxable_001": _portfolio(1_000_000),
        "acc_nisa_001": _portfolio(500_000),
    }
    return plan, portfolios


class ChartBuilderTest(unittest.TestCase):
    def test_series_grouped_by_account_type_plus_unallocated_surplus(self) -> None:
        plan, portfolios = _plan_with_two_account_types()
        result = run_projection(plan, portfolios, zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules())

        chart = build_networth_chart(plan, result)

        self.assertEqual(chart["type"], "stacked_area")
        series_names = {series["name"] for series in chart["series"]}
        self.assertEqual(series_names, {"taxable", "nisa_growth", "unallocated_surplus"})

        first_year_totals = {series["name"]: series["values"][0] for series in chart["series"]}
        self.assertEqual(first_year_totals["taxable"], 1_050_000)
        # 月次複利を12回繰り返す過程での円未満丸めにより、単純な年率複利(525,000円)と1円だけずれうる
        self.assertEqual(first_year_totals["nisa_growth"], 524_999)
        # unallocated_surplusはどの資産クラスとして運用されるか不明なためゼロ成長で扱う
        # （複利せず、毎月の余剰(1,000,000/12)を単純合算した額に丸め差1円だけ届かない）
        self.assertEqual(first_year_totals["unallocated_surplus"], 999_996)

    def test_series_values_sum_to_networth(self) -> None:
        plan, portfolios = _plan_with_two_account_types()
        result = run_projection(plan, portfolios, zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules())
        chart = build_networth_chart(plan, result)

        for index, projection in enumerate(result.yearly_projections):
            total = sum(series["values"][index] for series in chart["series"])
            self.assertEqual(total, int(projection.networth.amount))


if __name__ == "__main__":
    unittest.main()
