import unittest
from datetime import date

from core.domain.montecarlo_result import MonteCarloResult, PercentileBand
from core.domain.pension import ClaimTiming, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from reports.montecarlo_report_builder import build_percentile_band_chart
from tests.portfolio_test_fixtures import no_allocation_contribution_strategy


def _plan_with_birth_date(birth_date: date) -> Plan:
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(age=65),
    )
    return Plan(
        plan_id="plan_test",
        name="テストプラン",
        user=User(birth_date=birth_date),
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.zero()),
        accounts=[],
        tax_config=TaxConfig(),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[]),
        contribution_strategy=no_allocation_contribution_strategy(),
    )


class BuildPercentileBandChartTest(unittest.TestCase):
    def test_builds_chart_from_percentile_bands(self) -> None:
        plan = _plan_with_birth_date(date(1990, 4, 1))
        result = MonteCarloResult(
            trials=100,
            success_count=87,
            success_rate=0.87,
            percentile_networth_by_year={
                2026: PercentileBand(p10=Money.of(1_000_000), p50=Money.of(2_000_000), p90=Money.of(3_000_000)),
                2027: PercentileBand(p10=Money.of(1_100_000), p50=Money.of(2_200_000), p90=Money.of(3_300_000)),
            },
        )

        chart = build_percentile_band_chart(plan, result)

        self.assertEqual(chart["type"], "percentile_band")
        self.assertEqual(chart["x"], [2026, 2027])
        self.assertEqual(chart["ages"], [36, 37])
        self.assertEqual(chart["p10"], [1_000_000, 1_100_000])
        self.assertEqual(chart["p50"], [2_000_000, 2_200_000])
        self.assertEqual(chart["p90"], [3_000_000, 3_300_000])


if __name__ == "__main__":
    unittest.main()
