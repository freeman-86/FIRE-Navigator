import unittest

from repositories.asset_class_repository import load_asset_class_registry, load_asset_class_risk_order


class LoadAssetClassRiskOrderTest(unittest.TestCase):
    def test_returns_all_registry_asset_classes(self) -> None:
        registry = load_asset_class_registry()
        risk_order = load_asset_class_risk_order()

        self.assertEqual(set(risk_order), set(registry.keys()))

    def test_orders_from_highest_to_lowest_risk(self) -> None:
        # config/asset_classes.yaml上のrisk_rankは cash < bond_us_treasury < equity_sp500 < btc
        # （数字が大きいほどリスクが高い）。btcが最初、cashが最後に来るはず。
        risk_order = load_asset_class_risk_order()

        self.assertEqual(risk_order[0], "btc")
        self.assertEqual(risk_order[-1], "cash")


if __name__ == "__main__":
    unittest.main()
