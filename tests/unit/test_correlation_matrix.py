import unittest

from core.domain.asset import AssetClass
from core.simulation.montecarlo.correlation_matrix import compute_correlation_matrix
from tests.market_data_test_fixtures import small_dataset


class ComputeCorrelationMatrixTest(unittest.TestCase):
    def test_correlation_matches_hand_calculation(self) -> None:
        matrix = compute_correlation_matrix(small_dataset())

        correlation = matrix.get(AssetClass.DOMESTIC_EQUITY, AssetClass.DOMESTIC_BOND)
        self.assertAlmostEqual(correlation, 0.8, places=6)

    def test_correlation_is_symmetric(self) -> None:
        matrix = compute_correlation_matrix(small_dataset())

        forward = matrix.get(AssetClass.DOMESTIC_EQUITY, AssetClass.DOMESTIC_BOND)
        backward = matrix.get(AssetClass.DOMESTIC_BOND, AssetClass.DOMESTIC_EQUITY)
        self.assertEqual(forward, backward)

    def test_self_correlation_is_one(self) -> None:
        matrix = compute_correlation_matrix(small_dataset())
        self.assertEqual(matrix.get(AssetClass.DOMESTIC_EQUITY, AssetClass.DOMESTIC_EQUITY), 1.0)


if __name__ == "__main__":
    unittest.main()
