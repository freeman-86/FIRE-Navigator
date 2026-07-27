import os
import unittest

from adapters.sheets.sheets_input_adapter import DEFAULT_CREDENTIALS_PATH, load_plan, load_portfolios
from core.domain.account import AccountType
from core.domain.plan import Plan

# このシートには利用者の実データが入っている可能性があるため、値を仮定した検証は行わず、
# Sheets Adapterが「何が入っていても構造的に正しく読み込めているか」だけを検証する
# （固定サンプル値との比較はtests/unit/test_sheets_input_adapter*.pyのフェイクシートで行う）。


@unittest.skipUnless(
    os.path.exists(DEFAULT_CREDENTIALS_PATH),
    "Google Sheets認証キー(secrets/gsheets_credentials.json)がないためスキップ",
)
class SheetsInputAdapterIntegrationTest(unittest.TestCase):
    def test_build_plan_from_test_spreadsheet(self) -> None:
        plan = load_plan()

        self.assertIsInstance(plan, Plan)
        self.assertTrue(plan.plan_id)

        self.assertTrue(plan.accounts, "入力_口座から1件も口座が読み込めませんでした")
        for account in plan.accounts:
            self.assertTrue(account.account_id)
            self.assertIsInstance(account.account_type, AccountType)

        for income in plan.incomes:
            self.assertTrue(income.source)
            self.assertGreaterEqual(income.amount.amount, 0)

        for expense in plan.expenses:
            self.assertTrue(expense.category)
            self.assertGreaterEqual(expense.amount.amount, 0)

    def test_load_portfolios_are_keyed_by_account_id(self) -> None:
        plan = load_plan()
        portfolios = load_portfolios()

        self.assertEqual(set(portfolios.keys()), {account.account_id for account in plan.accounts})
        for portfolio in portfolios.values():
            self.assertTrue(portfolio.holdings, "口座に紐づくholdingsが1件もありません")
            for holding in portfolio.holdings:
                self.assertGreaterEqual(holding.current_value.amount, 0)
                self.assertGreaterEqual(holding.cost_basis.amount, 0)


if __name__ == "__main__":
    unittest.main()
