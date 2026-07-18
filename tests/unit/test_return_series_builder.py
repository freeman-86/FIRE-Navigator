import unittest
from decimal import Decimal

from core.domain.asset import AssetClass
from core.simulation.historical.return_series_builder import build_return_series
from tests.market_data_test_fixtures import small_dataset


class BuildReturnSeriesTest(unittest.TestCase):
    def test_slices_correct_years_for_window(self) -> None:
        series = build_return_series(small_dataset(), window_start_year=2002, window_length=2)

        values = [r.value for r in series[AssetClass.DOMESTIC_EQUITY]]
        self.assertEqual(values, [Decimal("-0.10"), Decimal("0.20")])

    def test_returns_all_asset_classes(self) -> None:
        series = build_return_series(small_dataset(), window_start_year=2001, window_length=1)
        self.assertEqual(set(series.keys()), {AssetClass.DOMESTIC_EQUITY, AssetClass.DOMESTIC_BOND})


if __name__ == "__main__":
    unittest.main()
