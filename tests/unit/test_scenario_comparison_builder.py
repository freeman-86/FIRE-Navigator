import unittest

from core.domain.simulation_result import SimulationResult, YearlyProjection
from core.domain.value_objects import Money
from reports.scenario_comparison_builder import build_scenario_comparison_chart


def _result(networths: list[int], start_year: int = 2026) -> SimulationResult:
    projections = [
        YearlyProjection(
            year=start_year + i,
            age_self=36 + i,
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
        for i, networth in enumerate(networths)
    ]
    return SimulationResult(yearly_projections=projections)


class BuildScenarioComparisonChartTest(unittest.TestCase):
    def test_one_series_per_scenario(self) -> None:
        results = {
            "60歳退職": _result([1_000_000, 2_000_000]),
            "65歳退職": _result([1_100_000, 2_300_000]),
        }

        chart = build_scenario_comparison_chart(results)

        self.assertEqual(chart["type"], "multi_line")
        self.assertEqual(chart["x"], [2026, 2027])
        series_by_name = {series["name"]: series["values"] for series in chart["series"]}
        self.assertEqual(series_by_name["60歳退職"], [1_000_000, 2_000_000])
        self.assertEqual(series_by_name["65歳退職"], [1_100_000, 2_300_000])

    def test_different_horizons_are_aligned_by_year_with_none_for_missing_years(self) -> None:
        results = {
            "60歳退職": _result([1_000_000, 2_000_000], start_year=2026),
            "65歳退職": _result([1_100_000, 2_300_000, 2_500_000], start_year=2026),
        }

        chart = build_scenario_comparison_chart(results)

        self.assertEqual(chart["x"], [2026, 2027, 2028])
        series_by_name = {series["name"]: series["values"] for series in chart["series"]}
        self.assertEqual(series_by_name["60歳退職"], [1_000_000, 2_000_000, None])
        self.assertEqual(series_by_name["65歳退職"], [1_100_000, 2_300_000, 2_500_000])


if __name__ == "__main__":
    unittest.main()
