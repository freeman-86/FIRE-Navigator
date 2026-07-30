import unittest

from adapters.local.local_data_adapter import _build_allocation_policy
from core.domain.errors import SchemaValidationError
from core.domain.value_objects import Rate

_REGISTRY = {"equity_sp500": "米国株式(S&P500)", "bond_us_treasury": "米国債", "btc": "BTC"}
# リスクが高い順（btc > equity_sp500 > bond_us_treasury）というテスト用の固定順。
# 実際の config/asset_classes.yaml のrisk_rankから独立させ、テストを設定ファイルの
# 値の変更から切り離す。
_RISK_ORDER = ["btc", "equity_sp500", "bond_us_treasury"]


class BuildAllocationPolicyTest(unittest.TestCase):
    def test_missing_section_returns_none(self) -> None:
        self.assertIsNone(_build_allocation_policy({}))

    def test_explicit_null_returns_none(self) -> None:
        self.assertIsNone(_build_allocation_policy({"allocation_policy": None}))

    def test_groups_weights_by_age_and_sorts_targets(self) -> None:
        data = {
            "allocation_policy": {
                "targets": [
                    {"age": 60, "weights": {"equity_sp500": "0.4", "bond_us_treasury": "0.6"}},
                    {"age": 30, "weights": {"equity_sp500": "0.8", "bond_us_treasury": "0.2"}},
                ]
            }
        }

        policy = _build_allocation_policy(data, asset_class_registry=_REGISTRY, asset_class_risk_order=_RISK_ORDER)

        self.assertEqual([target.age for target in policy.targets], [30, 60])
        self.assertEqual(policy.targets[0].weights, {"equity_sp500": Rate.of("0.8"), "bond_us_treasury": Rate.of("0.2")})

    def test_weights_key_order_follows_risk_order_not_input_order(self) -> None:
        # core/simulation/withdrawal/withdrawal_engine.pyのオーバーウェイト優先売却は
        # target_weightsの辞書順で資産クラスを走査するため、複数の資産クラスが同時に
        # オーバーウェイトな場合にどれを先に取り崩すかはこの順序で決まる。入力JSONのキー順
        # （手編集やフォーム再保存で変わりうる）には左右されず、リスクが高い資産クラスから
        # 先に取り崩されるよう、常にrisk_rank順に正規化されている必要がある。
        data = {
            "allocation_policy": {
                "targets": [
                    {"age": 30, "weights": {"bond_us_treasury": "0.2", "equity_sp500": "0.75", "btc": "0.05"}}
                ]
            }
        }

        policy = _build_allocation_policy(data, asset_class_registry=_REGISTRY, asset_class_risk_order=_RISK_ORDER)

        self.assertEqual(list(policy.targets[0].weights.keys()), ["btc", "equity_sp500", "bond_us_treasury"])

    def test_unknown_asset_class_in_weights_raises_schema_validation_error(self) -> None:
        data = {"allocation_policy": {"targets": [{"age": 30, "weights": {"gold": "1.0"}}]}}

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_allocation_policy(data, asset_class_registry=_REGISTRY, asset_class_risk_order=_RISK_ORDER)
        self.assertEqual(ctx.exception.field_path, "allocation_policy.targets[0].weights")

    def test_missing_age_raises_schema_validation_error(self) -> None:
        data = {"allocation_policy": {"targets": [{"weights": {"equity_sp500": "1.0"}}]}}

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_allocation_policy(data, asset_class_registry=_REGISTRY, asset_class_risk_order=_RISK_ORDER)
        self.assertEqual(ctx.exception.field_path, "allocation_policy.targets[0].age")


if __name__ == "__main__":
    unittest.main()
