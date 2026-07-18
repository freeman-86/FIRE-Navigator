import unittest

from core.domain.progress_record import ProgressRecord
from core.domain.simulation_result import SimulationResult, YearlyProjection
from core.domain.value_objects import Money
from reports.progress_comparison_builder import build_progress_comparison_chart


def _projection(year: int, networth: int) -> YearlyProjection:
    return YearlyProjection(
        year=year,
        age_self=36,
        gross_income=Money.zero(),
        pension_income=Money.zero(),
        income_tax=Money.zero(),
        resident_tax=Money.zero(),
        social_insurance=Money.zero(),
        net_income=Money.zero(),
        total_expense=Money.zero(),
        net_cashflow=Money.zero(),
        account_balances={},
        networth=Money.of(networth),
    )


class BuildProgressComparisonChartTest(unittest.TestCase):
    def test_aligns_planned_and_actual_by_year(self) -> None:
        planned = SimulationResult(
            yearly_projections=[_projection(2026, 1_000_000), _projection(2027, 2_000_000), _projection(2028, 3_000_000)]
        )
        actual = [ProgressRecord(year=2026, actual_networth=Money.of(950_000)), ProgressRecord(year=2027, actual_networth=Money.of(2_200_000))]

        chart = build_progress_comparison_chart(planned, actual)

        self.assertEqual(chart["x"], [2026, 2027, 2028])
        series_by_name = {s["name"]: s["values"] for s in chart["series"]}
        self.assertEqual(series_by_name["計画"], [1_000_000, 2_000_000, 3_000_000])
        self.assertEqual(series_by_name["実績"], [950_000, 2_200_000, None])

    def test_actual_only_year_is_included(self) -> None:
        planned = SimulationResult(yearly_projections=[_projection(2026, 1_000_000)])
        actual = [ProgressRecord(year=2027, actual_networth=Money.of(1_100_000))]

        chart = build_progress_comparison_chart(planned, actual)

        self.assertEqual(chart["x"], [2026, 2027])


if __name__ == "__main__":
    unittest.main()
