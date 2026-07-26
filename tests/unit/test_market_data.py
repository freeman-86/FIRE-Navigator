import unittest

from core.domain.market_data import filter_from_year
from tests.market_data_test_fixtures import small_dataset


class FilterFromYearTest(unittest.TestCase):
    def test_keeps_only_years_at_or_after_start_year(self) -> None:
        filtered = filter_from_year(small_dataset(), 2003)

        self.assertEqual(filtered.start_year, 2003)
        self.assertEqual(filtered.end_year, small_dataset().end_year)
        for series in filtered.series_by_asset_class.values():
            self.assertEqual(set(series.returns_by_year.keys()), {2003, 2004})

    def test_preserves_source_and_verified_metadata(self) -> None:
        filtered = filter_from_year(small_dataset(), 2003)

        equity = filtered.series_by_asset_class["domestic_equity"]
        self.assertEqual(equity.source, "test")
        self.assertTrue(equity.verified)

    def test_does_not_mutate_original_dataset(self) -> None:
        original = small_dataset()

        filter_from_year(original, 2003)

        self.assertEqual(set(original.series_by_asset_class["domestic_equity"].returns_by_year.keys()), {2001, 2002, 2003, 2004})

    def test_returns_empty_years_when_start_year_is_after_dataset_end(self) -> None:
        filtered = filter_from_year(small_dataset(), 2010)

        for series in filtered.series_by_asset_class.values():
            self.assertEqual(series.returns_by_year, {})


if __name__ == "__main__":
    unittest.main()
