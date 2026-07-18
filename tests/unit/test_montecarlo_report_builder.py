import unittest

from core.domain.montecarlo_result import MonteCarloResult, PercentileBand
from core.domain.value_objects import Money
from reports.montecarlo_report_builder import build_percentile_band_chart


class BuildPercentileBandChartTest(unittest.TestCase):
    def test_builds_chart_from_percentile_bands(self) -> None:
        result = MonteCarloResult(
            trials=100,
            success_count=87,
            success_rate=0.87,
            percentile_networth_by_year={
                2026: PercentileBand(p10=Money.of(1_000_000), p50=Money.of(2_000_000), p90=Money.of(3_000_000)),
                2027: PercentileBand(p10=Money.of(1_100_000), p50=Money.of(2_200_000), p90=Money.of(3_300_000)),
            },
        )

        chart = build_percentile_band_chart(result)

        self.assertEqual(chart["type"], "percentile_band")
        self.assertEqual(chart["x"], [2026, 2027])
        self.assertEqual(chart["p10"], [1_000_000, 1_100_000])
        self.assertEqual(chart["p50"], [2_000_000, 2_200_000])
        self.assertEqual(chart["p90"], [3_000_000, 3_300_000])


if __name__ == "__main__":
    unittest.main()
