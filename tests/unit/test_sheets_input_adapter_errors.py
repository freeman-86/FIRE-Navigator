import unittest

from adapters.sheets.sheets_input_adapter import (
    _build_accounts,
    _build_incomes,
    _build_user,
)
from adapters.sheets.sheet_mapping import (
    ACCOUNT_ID_HEADER,
    ACCOUNT_TYPE_HEADER,
    ACCOUNTS_SHEET,
    AMOUNT_ANNUAL_HEADER,
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    BIRTH_DATE_HEADER,
    EXPECTED_RETURN_HEADER,
    GROWTH_RATE_HEADER,
    INCOME_ID_HEADER,
    INCOMES_SHEET,
    MONTHLY_CONTRIBUTION_HEADER,
    PLAN_SHEET,
    PLAN_START_CONDITION_LABEL,
    SOURCE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
    END_TYPE_HEADER,
    END_VALUE_HEADER,
)
from core.domain.errors import StructuralInputError
from core.domain.value_objects import Money, Rate


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
        settings = {}
        with self.assertRaises(StructuralInputError) as ctx:
            _build_user(settings)
        self.assertEqual(ctx.exception.field_path, f"{PLAN_SHEET}!{BIRTH_DATE_HEADER}")

    def test_malformed_birth_date_raises_structural_input_error(self) -> None:
        settings = {BIRTH_DATE_HEADER: "1990/04/01"}
        with self.assertRaises(StructuralInputError):
            _build_user(settings)


class BuildAccountsErrorTest(unittest.TestCase):
    def test_invalid_account_type_raises_error_with_row_field_path(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                ACCOUNTS_SHEET: _FakeWorksheet(
                    records=[
                        {
                            ACCOUNT_ID_HEADER: "acc_001",
                            ACCOUNT_TYPE_HEADER: "not_a_real_type",
                            BALANCE_HEADER: "1000000",
                            ASSET_CLASS_HEADER: "cash",
                            EXPECTED_RETURN_HEADER: "0.01",
                            MONTHLY_CONTRIBUTION_HEADER: "",
                        }
                    ]
                )
            }
        )
        with self.assertRaises(StructuralInputError) as ctx:
            _build_accounts(spreadsheet)
        self.assertEqual(ctx.exception.field_path, f"{ACCOUNTS_SHEET}!row2.{ACCOUNT_TYPE_HEADER}")

    def test_missing_account_id_raises_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {ACCOUNTS_SHEET: _FakeWorksheet(records=[{ACCOUNT_TYPE_HEADER: "cash"}])}
        )
        with self.assertRaises(StructuralInputError) as ctx:
            _build_accounts(spreadsheet)
        self.assertEqual(ctx.exception.field_path, f"{ACCOUNTS_SHEET}!row2.{ACCOUNT_ID_HEADER}")


class BuildIncomesErrorTest(unittest.TestCase):
    def test_non_numeric_amount_raises_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "not_a_number",
                            GROWTH_RATE_HEADER: "0.01",
                            START_TYPE_HEADER: PLAN_START_CONDITION_LABEL,
                            START_VALUE_HEADER: "",
                            END_TYPE_HEADER: "",
                            END_VALUE_HEADER: "",
                        }
                    ]
                )
            }
        )
        with self.assertRaises(StructuralInputError) as ctx:
            _build_incomes(spreadsheet, Rate.zero())
        self.assertEqual(ctx.exception.field_path, f"{INCOMES_SHEET}!row2.{AMOUNT_ANNUAL_HEADER}")

    def test_missing_start_type_raises_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "1000000",
                            GROWTH_RATE_HEADER: "0.01",
                            START_TYPE_HEADER: "",
                            START_VALUE_HEADER: "",
                        }
                    ]
                )
            }
        )
        with self.assertRaises(StructuralInputError):
            _build_incomes(spreadsheet, Rate.zero())


class BuildIncomesGrowthRateDefaultTest(unittest.TestCase):
    def test_blank_growth_rate_defaults_to_inflation_rate(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "1000000",
                            GROWTH_RATE_HEADER: "",
                            START_TYPE_HEADER: PLAN_START_CONDITION_LABEL,
                            START_VALUE_HEADER: "",
                        }
                    ]
                )
            }
        )

        incomes = _build_incomes(spreadsheet, Rate.of("0.02"))

        self.assertEqual(incomes[0].growth_rate, Rate.of("0.02"))

    def test_explicit_growth_rate_takes_priority_over_inflation_rate(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "1000000",
                            GROWTH_RATE_HEADER: "0.01",
                            START_TYPE_HEADER: PLAN_START_CONDITION_LABEL,
                            START_VALUE_HEADER: "",
                        }
                    ]
                )
            }
        )

        incomes = _build_incomes(spreadsheet, Rate.of("0.02"))

        self.assertEqual(incomes[0].growth_rate, Rate.of("0.01"))

    def test_blank_amount_defaults_to_zero_instead_of_raising(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "",
                            GROWTH_RATE_HEADER: "0.01",
                            START_TYPE_HEADER: PLAN_START_CONDITION_LABEL,
                            START_VALUE_HEADER: "",
                        }
                    ]
                )
            }
        )

        incomes = _build_incomes(spreadsheet, Rate.of("0.02"))

        self.assertEqual(incomes[0].amount, Money.zero())


if __name__ == "__main__":
    unittest.main()
