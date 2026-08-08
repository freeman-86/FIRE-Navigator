import unittest

from core.domain.simulation_result import SimulationResult, YearlyProjection
from core.domain.value_objects import Money
from core.simulation.montecarlo.statistics import compute_statistics


def _trial(year: int, networth: int, unallocated_surplus: int = 0) -> SimulationResult:
    return SimulationResult(
        yearly_projections=[
            YearlyProjection(
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
                account_balances={"unallocated_surplus": Money.of(unallocated_surplus)},
                networth=Money.of(networth),
            )
        ]
    )


class ComputeStatisticsTest(unittest.TestCase):
    def test_success_rate_reflects_failed_trials(self) -> None:
        trials = [_trial(2026, 1_000_000), _trial(2026, 2_000_000), _trial(2026, -500_000, unallocated_surplus=-500_000)]

        result = compute_statistics(trials)

        self.assertEqual(result.trials, 3)
        self.assertEqual(result.success_count, 2)
        self.assertAlmostEqual(result.success_rate, 2 / 3)

    def test_percentile_band_uses_sorted_networth(self) -> None:
        trials = [_trial(2026, v * 10) for v in range(1, 21)]

        result = compute_statistics(trials)
        band = result.percentile_networth_by_year[2026]

        # 20件中: p5->index1(20), p10->index2(30), p20->index4(50), p30->index6(70),
        # p50->index10(110), p70->index14(150), p80->index16(170), p90->index18(190), p95->index19(200)
        self.assertEqual(band.p5, Money.of(20))
        self.assertEqual(band.p10, Money.of(30))
        self.assertEqual(band.p20, Money.of(50))
        self.assertEqual(band.p30, Money.of(70))
        self.assertEqual(band.p50, Money.of(110))
        self.assertEqual(band.p70, Money.of(150))
        self.assertEqual(band.p80, Money.of(170))
        self.assertEqual(band.p90, Money.of(190))
        self.assertEqual(band.p95, Money.of(200))

    def test_empty_trials_returns_zero_success_rate(self) -> None:
        result = compute_statistics([])
        self.assertEqual(result.trials, 0)
        self.assertEqual(result.success_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
