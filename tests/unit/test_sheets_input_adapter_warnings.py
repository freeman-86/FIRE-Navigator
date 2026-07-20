import unittest

import gspread

from adapters.sheets.sheet_mapping import (
    AMOUNT_ANNUAL_HEADER,
    CATEGORY_HEADER,
    END_TYPE_HEADER,
    END_VALUE_HEADER,
    EXPENSE_AMOUNT_HEADER,
    EXPENSE_ID_HEADER,
    EXPENSES_SHEET,
    GROWTH_RATE_HEADER,
    INCOME_ID_HEADER,
    INCOMES_SHEET,
    IS_FLEXIBLE_HEADER,
    ONE_TIME_FLAG_HEADER,
    SOURCE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
)
from adapters.sheets.sheets_input_adapter import collect_input_warnings


class _FakeWorksheet:
    def __init__(self, records):
        self._records = records

    def get_all_records(self):
        return self._records


class _FakeSpreadsheet:
    def __init__(self, worksheets: dict):
        self._worksheets = worksheets

    def worksheet(self, name):
        if name not in self._worksheets:
            raise gspread.exceptions.WorksheetNotFound(name)
        return self._worksheets[name]


class CollectExpensesWarningsTest(unittest.TestCase):
    def test_warns_when_one_time_row_has_growth_rate_or_is_flexible(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EXPENSE_ID_HEADER: "expense_car",
                            CATEGORY_HEADER: "車",
                            ONE_TIME_FLAG_HEADER: "TRUE",
                            EXPENSE_AMOUNT_HEADER: "3000000",
                            GROWTH_RATE_HEADER: "0.02",
                            IS_FLEXIBLE_HEADER: "TRUE",
                            START_TYPE_HEADER: "age",
                            START_VALUE_HEADER: "45",
                        }
                    ]
                )
            }
        )

        warnings = collect_input_warnings(spreadsheet)

        field_paths = {w.field_path for w in warnings}
        self.assertIn(f"{EXPENSES_SHEET}!row2.{GROWTH_RATE_HEADER}", field_paths)
        self.assertIn(f"{EXPENSES_SHEET}!row2.{IS_FLEXIBLE_HEADER}", field_paths)

    def test_warns_when_recurring_row_has_start_condition(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EXPENSE_ID_HEADER: "expense_living",
                            CATEGORY_HEADER: "living",
                            ONE_TIME_FLAG_HEADER: "FALSE",
                            EXPENSE_AMOUNT_HEADER: "3600000",
                            GROWTH_RATE_HEADER: "0.02",
                            START_TYPE_HEADER: "age",
                            START_VALUE_HEADER: "45",
                        }
                    ]
                )
            }
        )

        warnings = collect_input_warnings(spreadsheet)

        field_paths = {w.field_path for w in warnings}
        self.assertIn(f"{EXPENSES_SHEET}!row2.{START_TYPE_HEADER}", field_paths)
        self.assertIn(f"{EXPENSES_SHEET}!row2.{START_VALUE_HEADER}", field_paths)

    def test_no_warnings_for_clean_rows(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EXPENSE_ID_HEADER: "expense_living",
                            CATEGORY_HEADER: "living",
                            ONE_TIME_FLAG_HEADER: "FALSE",
                            EXPENSE_AMOUNT_HEADER: "3600000",
                            GROWTH_RATE_HEADER: "0.02",
                            START_TYPE_HEADER: "",
                            START_VALUE_HEADER: "",
                        },
                        {
                            EXPENSE_ID_HEADER: "expense_car",
                            CATEGORY_HEADER: "車",
                            ONE_TIME_FLAG_HEADER: "TRUE",
                            EXPENSE_AMOUNT_HEADER: "3000000",
                            GROWTH_RATE_HEADER: "",
                            START_TYPE_HEADER: "age",
                            START_VALUE_HEADER: "45",
                        },
                    ]
                )
            }
        )

        warnings = collect_input_warnings(spreadsheet)

        self.assertEqual(warnings, [])

    def test_missing_sheet_returns_no_warnings(self) -> None:
        self.assertEqual(collect_input_warnings(_FakeSpreadsheet({})), [])


class CollectIncomesWarningsTest(unittest.TestCase):
    def test_warns_when_end_value_present_but_end_type_missing(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "6000000",
                            END_TYPE_HEADER: "",
                            END_VALUE_HEADER: "60",
                        }
                    ]
                )
            }
        )

        warnings = collect_input_warnings(spreadsheet)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].field_path, f"{INCOMES_SHEET}!row2.{END_VALUE_HEADER}")

    def test_no_warning_when_end_type_and_value_both_present(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "6000000",
                            END_TYPE_HEADER: "age",
                            END_VALUE_HEADER: "60",
                        }
                    ]
                )
            }
        )

        warnings = collect_input_warnings(spreadsheet)

        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
