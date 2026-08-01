import unittest

from adapters.local.local_data_adapter import _build_accounts, build_portfolios_from_local_file
from core.domain.account import AccountType
from core.domain.errors import SchemaValidationError
from core.domain.value_objects import Money, Rate

_REGISTRY = {"cash": "現金", "equity_sp500": "米国株式(S&P500)", "bond_us_treasury": "米国債"}


class BuildAccountsTest(unittest.TestCase):
    def test_reads_account_id_and_type(self) -> None:
        data = {"accounts": [{"account_id": "acc_1", "account_type": "cash"}]}

        accounts = _build_accounts(data)

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].account_id, "acc_1")
        self.assertEqual(accounts[0].account_type, AccountType.CASH)
        self.assertIsNone(accounts[0].monthly_contribution)

    def test_monthly_contribution_is_optional(self) -> None:
        data = {"accounts": [{"account_id": "acc_1", "account_type": "nisa_growth", "monthly_contribution": 50000}]}

        accounts = _build_accounts(data)

        self.assertEqual(accounts[0].monthly_contribution, Money.of(50_000))

    def test_unknown_account_type_raises_schema_validation_error(self) -> None:
        data = {"accounts": [{"account_id": "acc_1", "account_type": "bitcoin_wallet"}]}

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_accounts(data)
        self.assertEqual(ctx.exception.field_path, "accounts[0].account_type")

    def test_missing_account_id_raises_schema_validation_error(self) -> None:
        with self.assertRaises(SchemaValidationError) as ctx:
            _build_accounts({"accounts": [{"account_type": "cash"}]})
        self.assertEqual(ctx.exception.field_path, "accounts[0].account_id")

    def test_no_accounts_key_returns_empty_list(self) -> None:
        self.assertEqual(_build_accounts({}), [])

    def test_duplicate_account_id_raises_schema_validation_error(self) -> None:
        # account_idはPortfolio Aggregateのdictキーとして使われるため、重複すると後の行が
        # 前の行を無言で上書きしてその口座の残高がシミュレーションから丸ごと消える
        # （現在の純資産等が実際より少なく表示される不具合の実例）。事故を未然に防ぐため拒否する。
        data = {
            "accounts": [
                {"account_id": "acc_1", "account_type": "cash"},
                {"account_id": "acc_2", "account_type": "cash"},
                {"account_id": "acc_1", "account_type": "taxable"},
            ]
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_accounts(data)
        self.assertEqual(ctx.exception.field_path, "accounts[2].account_id")


class BuildPortfoliosFromLocalFileTest(unittest.TestCase):
    def test_builds_one_holding_per_account(self) -> None:
        data = {
            "accounts": [
                {
                    "account_id": "acc_1",
                    "account_type": "taxable",
                    "asset_class": "equity_sp500",
                    "expected_return": "0.05",
                    "current_value": 1000000,
                }
            ]
        }

        portfolios = build_portfolios_from_local_file(data, asset_class_registry=_REGISTRY)

        self.assertEqual(set(portfolios.keys()), {"acc_1"})
        holding = portfolios["acc_1"].holdings[0]
        self.assertEqual(holding.asset.asset_class, "equity_sp500")
        self.assertEqual(holding.asset.expected_return, Rate.of("0.05"))
        self.assertEqual(holding.current_value, Money.of(1_000_000))

    def test_blank_current_value_defaults_to_zero(self) -> None:
        data = {
            "accounts": [
                {"account_id": "acc_1", "account_type": "cash", "asset_class": "cash", "expected_return": "0.0"}
            ]
        }

        portfolios = build_portfolios_from_local_file(data, asset_class_registry=_REGISTRY)

        self.assertEqual(portfolios["acc_1"].holdings[0].current_value, Money.zero())

    def test_blank_cost_basis_defaults_to_current_value(self) -> None:
        # 取得原価が未入力の場合は残高と同額とみなす（開始時点の含み益ゼロという後方互換のデフォルト）
        data = {
            "accounts": [
                {
                    "account_id": "acc_1",
                    "account_type": "taxable",
                    "asset_class": "equity_sp500",
                    "expected_return": "0.05",
                    "current_value": 2000000,
                }
            ]
        }

        portfolios = build_portfolios_from_local_file(data, asset_class_registry=_REGISTRY)

        holding = portfolios["acc_1"].holdings[0]
        self.assertEqual(holding.cost_basis, holding.current_value)

    def test_explicit_cost_basis_is_used(self) -> None:
        data = {
            "accounts": [
                {
                    "account_id": "acc_1",
                    "account_type": "taxable",
                    "asset_class": "equity_sp500",
                    "expected_return": "0.05",
                    "current_value": 2000000,
                    "cost_basis": 1500000,
                }
            ]
        }

        portfolios = build_portfolios_from_local_file(data, asset_class_registry=_REGISTRY)

        self.assertEqual(portfolios["acc_1"].holdings[0].cost_basis, Money.of(1_500_000))

    def test_unknown_asset_class_raises_schema_validation_error(self) -> None:
        data = {
            "accounts": [
                {
                    "account_id": "acc_1",
                    "account_type": "taxable",
                    "asset_class": "gold_bars",
                    "expected_return": "0.05",
                }
            ]
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            build_portfolios_from_local_file(data, asset_class_registry=_REGISTRY)
        self.assertEqual(ctx.exception.field_path, "accounts[0].asset_class")

    def test_missing_expected_return_raises_schema_validation_error(self) -> None:
        data = {"accounts": [{"account_id": "acc_1", "account_type": "cash", "asset_class": "cash"}]}

        with self.assertRaises(SchemaValidationError) as ctx:
            build_portfolios_from_local_file(data, asset_class_registry=_REGISTRY)
        self.assertEqual(ctx.exception.field_path, "accounts[0].expected_return")

    def test_duplicate_account_id_raises_schema_validation_error(self) -> None:
        data = {
            "accounts": [
                {
                    "account_id": "acc_1",
                    "account_type": "taxable",
                    "asset_class": "equity_sp500",
                    "expected_return": "0.05",
                    "current_value": 1_000_000,
                },
                {
                    "account_id": "acc_1",
                    "account_type": "taxable",
                    "asset_class": "equity_sp500",
                    "expected_return": "0.05",
                    "current_value": 2_000_000,
                },
            ]
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            build_portfolios_from_local_file(data, asset_class_registry=_REGISTRY)
        self.assertEqual(ctx.exception.field_path, "accounts[1].account_id")


if __name__ == "__main__":
    unittest.main()
