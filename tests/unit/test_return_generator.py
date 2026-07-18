import unittest

from core.domain.asset import AssetClass
from core.simulation.montecarlo.correlation_matrix import CorrelationMatrix
from core.simulation.montecarlo.distribution import AssetReturnDistribution
from core.simulation.montecarlo.random_seed import create_rng
from core.simulation.montecarlo.return_generator import generate_annual_returns
from core.domain.value_objects import Rate


class GenerateAnnualReturnsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.asset_classes = [AssetClass.DOMESTIC_EQUITY, AssetClass.DOMESTIC_BOND]
        self.distributions = {
            AssetClass.DOMESTIC_EQUITY: AssetReturnDistribution(
                AssetClass.DOMESTIC_EQUITY, mean=Rate.from_percent(5), std_dev=Rate.from_percent(15)
            ),
            AssetClass.DOMESTIC_BOND: AssetReturnDistribution(
                AssetClass.DOMESTIC_BOND, mean=Rate.from_percent(1), std_dev=Rate.from_percent(3)
            ),
        }
        self.correlation_matrix = CorrelationMatrix({(AssetClass.DOMESTIC_EQUITY, AssetClass.DOMESTIC_BOND): 0.2})

    def test_same_seed_produces_identical_sequence(self) -> None:
        sequence_a = [
            generate_annual_returns(self.asset_classes, self.distributions, self.correlation_matrix, create_rng(42))
            for _ in range(5)
        ]
        sequence_b = [
            generate_annual_returns(self.asset_classes, self.distributions, self.correlation_matrix, create_rng(42))
            for _ in range(5)
        ]
        self.assertEqual(sequence_a, sequence_b)

    def test_different_seeds_produce_different_sequences(self) -> None:
        rng_a = create_rng(1)
        rng_b = create_rng(2)
        result_a = generate_annual_returns(self.asset_classes, self.distributions, self.correlation_matrix, rng_a)
        result_b = generate_annual_returns(self.asset_classes, self.distributions, self.correlation_matrix, rng_b)
        self.assertNotEqual(result_a, result_b)

    def test_returns_one_value_per_asset_class(self) -> None:
        rng = create_rng(7)
        result = generate_annual_returns(self.asset_classes, self.distributions, self.correlation_matrix, rng)
        self.assertEqual(set(result.keys()), set(self.asset_classes))


if __name__ == "__main__":
    unittest.main()
