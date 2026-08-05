import tempfile
import unittest
from pathlib import Path

import yaml

from core.domain.value_objects import Rate
from repositories.market_data_repository import load_historical_dataset


class LoadHistoricalDatasetTest(unittest.TestCase):
    def test_loads_committed_dataset_including_btc_historical_proxy(self) -> None:
        # btcはconfig/asset_classes.yamlのhistorical_proxy設定により、equity_sp500の系列を
        # 代用したエイリアスとして追加される（実データを持つ資産クラスと合わせて3つになる）。
        dataset = load_historical_dataset()

        self.assertEqual(dataset.start_year, 1928)
        self.assertEqual(dataset.end_year, 2024)
        self.assertEqual(set(dataset.series_by_asset_class.keys()), {"equity_sp500", "bond_us_treasury", "btc"})

    def test_both_real_series_are_verified(self) -> None:
        dataset = load_historical_dataset()

        self.assertTrue(dataset.series_by_asset_class["equity_sp500"].verified)
        self.assertTrue(dataset.series_by_asset_class["bond_us_treasury"].verified)

    def test_btc_proxy_series_is_not_verified(self) -> None:
        # 代用（実データではない）ことが分かるよう、verifiedはFalseにする。
        dataset = load_historical_dataset()

        self.assertFalse(dataset.series_by_asset_class["btc"].verified)

    def test_btc_proxy_series_mirrors_equity_sp500_values(self) -> None:
        dataset = load_historical_dataset()

        self.assertEqual(
            dataset.series_by_asset_class["btc"].returns_by_year,
            dataset.series_by_asset_class["equity_sp500"].returns_by_year,
        )

    def test_each_series_spans_the_full_dataset_range(self) -> None:
        dataset = load_historical_dataset()

        for series in dataset.series_by_asset_class.values():
            self.assertEqual(set(series.returns_by_year.keys()), set(range(dataset.start_year, dataset.end_year + 1)))


class LoadHistoricalDatasetProxyConfigTest(unittest.TestCase):
    """historical_proxyの適用ロジック自体を、コミット済みの実データではなく小さいテスト用の
    yamlで検証する（将来btc以外にもproxyが増えても壊れにくいように）。"""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.historical_path = Path(self._tmp_dir.name) / "historical_returns.yaml"
        self.asset_classes_path = Path(self._tmp_dir.name) / "asset_classes.yaml"

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _write_historical(self, asset_classes: dict) -> None:
        with open(self.historical_path, "w", encoding="utf-8") as f:
            yaml.safe_dump({"start_year": 2000, "end_year": 2002, "asset_classes": asset_classes}, f)

    def _write_asset_classes(self, asset_classes: dict) -> None:
        with open(self.asset_classes_path, "w", encoding="utf-8") as f:
            yaml.safe_dump({"schema_version": 1, "asset_classes": asset_classes}, f)

    def test_asset_class_without_own_data_is_not_added_when_no_proxy_configured(self) -> None:
        self._write_historical(
            {"equity_sp500": {"source": "test", "verified": True, "annual_returns": {2000: 0.1, 2001: 0.2, 2002: 0.3}}}
        )
        self._write_asset_classes({"gold": {"display_name": "金", "risk_rank": 2}})

        dataset = load_historical_dataset(self.historical_path, self.asset_classes_path)

        self.assertNotIn("gold", dataset.series_by_asset_class)

    def test_proxy_is_not_applied_when_target_already_has_its_own_data(self) -> None:
        # 代用元と代用先の両方に実データがある場合は、実データの方を優先し上書きしない。
        self._write_historical(
            {
                "equity_sp500": {"source": "s1", "verified": True, "annual_returns": {2000: 0.1, 2001: 0.2, 2002: 0.3}},
                "gold": {"source": "s2", "verified": True, "annual_returns": {2000: 0.05, 2001: 0.06, 2002: 0.07}},
            }
        )
        self._write_asset_classes(
            {"gold": {"display_name": "金", "risk_rank": 2, "historical_proxy": "equity_sp500"}}
        )

        dataset = load_historical_dataset(self.historical_path, self.asset_classes_path)

        self.assertTrue(dataset.series_by_asset_class["gold"].verified)
        self.assertEqual(dataset.series_by_asset_class["gold"].returns_by_year[2000], Rate.of(0.05))

    def test_proxy_pointing_to_nonexistent_asset_class_is_silently_skipped(self) -> None:
        self._write_historical(
            {"equity_sp500": {"source": "s1", "verified": True, "annual_returns": {2000: 0.1, 2001: 0.2, 2002: 0.3}}}
        )
        self._write_asset_classes({"gold": {"display_name": "金", "risk_rank": 2, "historical_proxy": "no_such_class"}})

        dataset = load_historical_dataset(self.historical_path, self.asset_classes_path)

        self.assertNotIn("gold", dataset.series_by_asset_class)


if __name__ == "__main__":
    unittest.main()
