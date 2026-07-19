import unittest
from decimal import Decimal

from core.domain.value_objects import Rate
from core.simulation.historical.scenario_builder import build_growth_rate_provider


class BuildGrowthRateProviderTest(unittest.TestCase):
    def test_blends_asset_classes_by_weight_and_returns_monthly_equivalent(self) -> None:
        return_series = {
            "domestic_equity": [Rate.of("0.10"), Rate.of("0.20")],
            "domestic_bond": [Rate.of("0.02"), Rate.of("0.00")],
        }
        weights = {"domestic_equity": Decimal("0.6"), "domestic_bond": Decimal("0.4")}

        provider = build_growth_rate_provider(return_series, weights)

        # 1年目(month_offset 0-11): 0.10*0.6 + 0.02*0.4 = 0.068 の月率換算値が12ヶ月続く
        expected_year0_monthly = Rate.of("0.068").monthly_equivalent()
        for month_offset in range(12):
            self.assertEqual(provider(month_offset).value, expected_year0_monthly.value)

        # 2年目(month_offset 12-23): 0.20*0.6 + 0.00*0.4 = 0.12 の月率換算値
        expected_year1_monthly = Rate.of("0.12").monthly_equivalent()
        self.assertEqual(provider(12).value, expected_year1_monthly.value)
        self.assertEqual(provider(23).value, expected_year1_monthly.value)

    def test_wraps_around_when_offset_exceeds_window_length(self) -> None:
        return_series = {"domestic_equity": [Rate.of("0.10"), Rate.of("0.20")]}
        weights = {"domestic_equity": Decimal("1")}

        provider = build_growth_rate_provider(return_series, weights)

        # window_length=2年=24ヶ月分のデータしかないため、それを超えるとオフセットが先頭へ巻き戻る
        self.assertEqual(provider(24), provider(0))
        self.assertEqual(provider(36), provider(12))


if __name__ == "__main__":
    unittest.main()
