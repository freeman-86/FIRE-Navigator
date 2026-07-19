import unittest

from repositories.market_data_repository import load_historical_dataset


class LoadHistoricalDatasetTest(unittest.TestCase):
    def test_loads_both_asset_classes_for_committed_dataset(self) -> None:
        dataset = load_historical_dataset()

        self.assertEqual(dataset.start_year, 2001)
        self.assertEqual(dataset.end_year, 2024)
        self.assertEqual(set(dataset.series_by_asset_class.keys()), {"equity_sp500", "bond_us_treasury"})

    def test_both_series_are_verified(self) -> None:
        dataset = load_historical_dataset()

        self.assertTrue(dataset.series_by_asset_class["equity_sp500"].verified)
        self.assertTrue(dataset.series_by_asset_class["bond_us_treasury"].verified)

    def test_each_series_spans_the_full_dataset_range(self) -> None:
        dataset = load_historical_dataset()

        for series in dataset.series_by_asset_class.values():
            self.assertEqual(set(series.returns_by_year.keys()), set(range(dataset.start_year, dataset.end_year + 1)))


if __name__ == "__main__":
    unittest.main()
