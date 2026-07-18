import unittest

from core.domain.asset import AssetClass
from repositories.market_data_repository import load_historical_dataset


class LoadHistoricalDatasetTest(unittest.TestCase):
    def test_loads_all_four_asset_classes_for_committed_dataset(self) -> None:
        dataset = load_historical_dataset()

        self.assertEqual(dataset.start_year, 2001)
        self.assertEqual(dataset.end_year, 2024)
        self.assertEqual(
            set(dataset.series_by_asset_class.keys()),
            {AssetClass.DOMESTIC_EQUITY, AssetClass.GLOBAL_EQUITY, AssetClass.DOMESTIC_BOND, AssetClass.GLOBAL_BOND},
        )

    def test_verified_flag_distinguishes_sourced_from_illustrative_series(self) -> None:
        dataset = load_historical_dataset()

        self.assertTrue(dataset.series_by_asset_class[AssetClass.DOMESTIC_EQUITY].verified)
        self.assertTrue(dataset.series_by_asset_class[AssetClass.GLOBAL_EQUITY].verified)
        self.assertFalse(dataset.series_by_asset_class[AssetClass.DOMESTIC_BOND].verified)
        self.assertFalse(dataset.series_by_asset_class[AssetClass.GLOBAL_BOND].verified)

    def test_each_series_spans_the_full_dataset_range(self) -> None:
        dataset = load_historical_dataset()

        for series in dataset.series_by_asset_class.values():
            self.assertEqual(set(series.returns_by_year.keys()), set(range(dataset.start_year, dataset.end_year + 1)))


if __name__ == "__main__":
    unittest.main()
