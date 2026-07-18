import unittest
from decimal import Decimal

from core.domain.asset import AssetClass
from core.domain.value_objects import Rate
from core.simulation.historical.scenario_builder import build_growth_rate_provider


class BuildGrowthRateProviderTest(unittest.TestCase):
    def test_blends_asset_classes_by_weight(self) -> None:
        return_series = {
            AssetClass.DOMESTIC_EQUITY: [Rate.of("0.10"), Rate.of("0.20")],
            AssetClass.DOMESTIC_BOND: [Rate.of("0.02"), Rate.of("0.00")],
        }
        weights = {AssetClass.DOMESTIC_EQUITY: Decimal("0.6"), AssetClass.DOMESTIC_BOND: Decimal("0.4")}

        provider = build_growth_rate_provider(return_series, weights)

        # year0: 0.10*0.6 + 0.02*0.4 = 0.06+0.008=0.068
        self.assertEqual(provider(0).value, Decimal("0.068"))
        # year1: 0.20*0.6 + 0.00*0.4 = 0.12
        self.assertEqual(provider(1).value, Decimal("0.12"))

    def test_wraps_around_when_offset_exceeds_window_length(self) -> None:
        return_series = {AssetClass.DOMESTIC_EQUITY: [Rate.of("0.10"), Rate.of("0.20")]}
        weights = {AssetClass.DOMESTIC_EQUITY: Decimal("1")}

        provider = build_growth_rate_provider(return_series, weights)

        self.assertEqual(provider(2), provider(0))
        self.assertEqual(provider(3), provider(1))


if __name__ == "__main__":
    unittest.main()
