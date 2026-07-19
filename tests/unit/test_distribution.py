import unittest
from decimal import Decimal

from core.simulation.montecarlo.distribution import distributions_from_historical_dataset, to_monthly_distributions
from tests.market_data_test_fixtures import small_dataset


class DistributionsFromHistoricalDatasetTest(unittest.TestCase):
    def test_mean_and_std_dev_match_hand_calculation(self) -> None:
        distributions = distributions_from_historical_dataset(small_dataset())

        equity = distributions["domestic_equity"]
        self.assertEqual(equity.mean.value, Decimal("0.05"))
        self.assertAlmostEqual(float(equity.std_dev.value), 0.129099, places=5)

        bond = distributions["domestic_bond"]
        self.assertEqual(bond.mean.value, Decimal("0.015"))
        self.assertAlmostEqual(float(bond.std_dev.value), 0.012910, places=5)


class ToMonthlyDistributionsTest(unittest.TestCase):
    def test_divides_mean_by_12_and_std_dev_by_sqrt_12(self) -> None:
        annual = distributions_from_historical_dataset(small_dataset())

        monthly = to_monthly_distributions(annual)

        equity = monthly["domestic_equity"]
        self.assertEqual(equity.mean.value, annual["domestic_equity"].mean.value / 12)
        self.assertAlmostEqual(
            float(equity.std_dev.value), float(annual["domestic_equity"].std_dev.value) / (12**0.5), places=9
        )

    def test_preserves_asset_class_keys(self) -> None:
        annual = distributions_from_historical_dataset(small_dataset())
        monthly = to_monthly_distributions(annual)
        self.assertEqual(set(monthly.keys()), set(annual.keys()))


if __name__ == "__main__":
    unittest.main()
