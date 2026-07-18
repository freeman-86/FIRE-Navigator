import unittest
from decimal import Decimal

from core.domain.asset import AssetClass
from core.simulation.montecarlo.distribution import distributions_from_historical_dataset
from tests.market_data_test_fixtures import small_dataset


class DistributionsFromHistoricalDatasetTest(unittest.TestCase):
    def test_mean_and_std_dev_match_hand_calculation(self) -> None:
        distributions = distributions_from_historical_dataset(small_dataset())

        equity = distributions[AssetClass.DOMESTIC_EQUITY]
        self.assertEqual(equity.mean.value, Decimal("0.05"))
        self.assertAlmostEqual(float(equity.std_dev.value), 0.129099, places=5)

        bond = distributions[AssetClass.DOMESTIC_BOND]
        self.assertEqual(bond.mean.value, Decimal("0.015"))
        self.assertAlmostEqual(float(bond.std_dev.value), 0.012910, places=5)


if __name__ == "__main__":
    unittest.main()
