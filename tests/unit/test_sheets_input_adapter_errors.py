import unittest

from adapters.sheets.sheets_input_adapter import (
    _build_accounts,
    _build_incomes,
    _build_user,
)
from adapters.sheets.sheet_mapping import ACCOUNTS_SHEET, INCOMES_SHEET
from core.domain.errors import StructuralInputError


class _FakeWorksheet:
    def __init__(self, records=None, values=None):
        self._records = records or []
        self._values = values or []

    def get_all_records(self):
        return self._records

    def get_all_values(self):
        return self._values


class _FakeSpreadsheet:
    def __init__(self, worksheets: dict):
        self._worksheets = worksheets

    def worksheet(self, name):
        return self._worksheets[name]


class BuildUserErrorTest(unittest.TestCase):
    def test_missing_birth_date_raises_structural_input_error_with_field_path(self) -> None:
        settings = {"residence": "tokyo"}
        with self.assertRaises(StructuralInputError) as ctx:
            _build_user(settings)
        self.assertEqual(ctx.exception.field_path, "Input_Plan!birth_date")

    def test_invalid_residence_raises_structural_input_error_listing_allowed_values(self) -> None:
        settings = {"birth_date": "1990-04-01", "residence": "narnia"}
        with self.assertRaises(StructuralInputError) as ctx:
            _build_user(settings)
        self.assertEqual(ctx.exception.field_path, "Input_Plan!residence")
        self.assertIn("tokyo", str(ctx.exception))

    def test_malformed_birth_date_raises_structural_input_error(self) -> None:
        settings = {"birth_date": "1990/04/01", "residence": "tokyo"}
        with self.assertRaises(StructuralInputError):
            _build_user(settings)


class BuildAccountsErrorTest(unittest.TestCase):
    def test_invalid_account_type_raises_error_with_row_field_path(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                ACCOUNTS_SHEET: _FakeWorksheet(
                    records=[
                        {
                            "account_id": "acc_001",
                            "account_type": "not_a_real_type",
                            "owner": "self",
                            "balance": "1000000",
                            "asset_class": "cash",
                            "expected_return": "0.01",
                            "volatility": "0.01",
                            "monthly_contribution": "",
                        }
                    ]
                )
            }
        )
        with self.assertRaises(StructuralInputError) as ctx:
            _build_accounts(spreadsheet)
        self.assertEqual(ctx.exception.field_path, f"{ACCOUNTS_SHEET}!row2.account_type")

    def test_missing_account_id_raises_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {ACCOUNTS_SHEET: _FakeWorksheet(records=[{"account_type": "cash", "owner": "self"}])}
        )
        with self.assertRaises(StructuralInputError) as ctx:
            _build_accounts(spreadsheet)
        self.assertEqual(ctx.exception.field_path, f"{ACCOUNTS_SHEET}!row2.account_id")


class BuildIncomesErrorTest(unittest.TestCase):
    def test_non_numeric_amount_raises_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            "income_id": "income_001",
                            "source": "salary",
                            "amount_annual": "not_a_number",
                            "growth_rate": "0.01",
                            "start_type": "plan_start",
                            "start_value": "",
                            "end_type": "",
                            "end_value": "",
                        }
                    ]
                )
            }
        )
        with self.assertRaises(StructuralInputError) as ctx:
            _build_incomes(spreadsheet)
        self.assertEqual(ctx.exception.field_path, f"{INCOMES_SHEET}!row2.amount_annual")

    def test_missing_start_type_raises_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            "income_id": "income_001",
                            "source": "salary",
                            "amount_annual": "1000000",
                            "growth_rate": "0.01",
                            "start_type": "",
                            "start_value": "",
                        }
                    ]
                )
            }
        )
        with self.assertRaises(StructuralInputError):
            _build_incomes(spreadsheet)


if __name__ == "__main__":
    unittest.main()
