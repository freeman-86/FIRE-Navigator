import unittest
from datetime import date

import gspread

from adapters.sheets.sheet_mapping import (
    BIRTH_DATE_HEADER,
    CATEGORY_HEADER,
    CHILD_ID_HEADER,
    EDUCATION_BAND_ID_HEADER,
    EDUCATION_EXPENSES_SHEET,
    END_AGE_HEADER,
    EXPENSE_AMOUNT_HEADER,
    EXPENSE_ID_HEADER,
    EXPENSES_SHEET,
    GROWTH_RATE_HEADER,
    MONTHLY_AMOUNT_HEADER,
    ONE_TIME_FLAG_HEADER,
    START_AGE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
)
from adapters.sheets.sheets_input_adapter import (
    _build_children_and_education_expenses,
    _build_expenses,
)
from core.domain.errors import StructuralInputError
from core.domain.value_objects import EventConditionType, Money


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


class BuildChildrenAndEducationExpensesTest(unittest.TestCase):
    def test_missing_sheet_returns_empty_lists(self) -> None:
        self.assertEqual(_build_children_and_education_expenses(_FakeSpreadsheet({})), ([], []))

    def test_reads_children_deduped_and_bands(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                EDUCATION_EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EDUCATION_BAND_ID_HEADER: "band_elementary",
                            CHILD_ID_HEADER: "child_001",
                            BIRTH_DATE_HEADER: "2020-04-01",
                            CATEGORY_HEADER: "小学校",
                            START_AGE_HEADER: "6",
                            END_AGE_HEADER: "11",
                            MONTHLY_AMOUNT_HEADER: "20000",
                        },
                        {
                            EDUCATION_BAND_ID_HEADER: "band_juku",
                            CHILD_ID_HEADER: "child_001",
                            BIRTH_DATE_HEADER: "2020-04-01",
                            CATEGORY_HEADER: "塾",
                            START_AGE_HEADER: "10",
                            END_AGE_HEADER: "11",
                            MONTHLY_AMOUNT_HEADER: "15000",
                        },
                    ]
                )
            }
        )

        children, bands = _build_children_and_education_expenses(spreadsheet)

        self.assertEqual(len(children), 1)  # 同じchild_idの行は1人に重複排除される
        self.assertEqual(children[0].child_id, "child_001")
        self.assertEqual(children[0].birth_date, date(2020, 4, 1))

        self.assertEqual(len(bands), 2)
        self.assertEqual(bands[0].child_id, "child_001")
        self.assertEqual(bands[0].start_age, 6)
        self.assertEqual(bands[0].end_age, 11)
        self.assertEqual(bands[0].monthly_amount, Money.of(20_000))

    def test_inconsistent_birth_date_for_same_child_id_raises_structural_input_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                EDUCATION_EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EDUCATION_BAND_ID_HEADER: "band_elementary",
                            CHILD_ID_HEADER: "child_001",
                            BIRTH_DATE_HEADER: "2020-04-01",
                            CATEGORY_HEADER: "小学校",
                            START_AGE_HEADER: "6",
                            END_AGE_HEADER: "11",
                            MONTHLY_AMOUNT_HEADER: "20000",
                        },
                        {
                            EDUCATION_BAND_ID_HEADER: "band_juku",
                            CHILD_ID_HEADER: "child_001",
                            BIRTH_DATE_HEADER: "2020-09-01",  # 生年月日が食い違う
                            CATEGORY_HEADER: "塾",
                            START_AGE_HEADER: "10",
                            END_AGE_HEADER: "11",
                            MONTHLY_AMOUNT_HEADER: "15000",
                        },
                    ]
                )
            }
        )

        with self.assertRaises(StructuralInputError) as ctx:
            _build_children_and_education_expenses(spreadsheet)
        self.assertEqual(ctx.exception.field_path, f"{EDUCATION_EXPENSES_SHEET}!row3.{BIRTH_DATE_HEADER}")


class BuildExpensesTest(unittest.TestCase):
    def test_recurring_row_becomes_expense(self) -> None:
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
                        }
                    ]
                )
            }
        )

        expenses, one_time_expenses = _build_expenses(spreadsheet)

        self.assertEqual(len(expenses), 1)
        self.assertEqual(one_time_expenses, [])
        self.assertEqual(expenses[0].category, "living")
        self.assertEqual(expenses[0].amount, Money.of(3_600_000))
        self.assertFalse(expenses[0].is_flexible)

    def test_blank_one_time_flag_defaults_to_recurring(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EXPENSE_ID_HEADER: "expense_living",
                            CATEGORY_HEADER: "living",
                            EXPENSE_AMOUNT_HEADER: "3600000",
                            GROWTH_RATE_HEADER: "0.02",
                        }
                    ]
                )
            }
        )

        expenses, one_time_expenses = _build_expenses(spreadsheet)

        self.assertEqual(len(expenses), 1)
        self.assertEqual(one_time_expenses, [])

    def test_one_time_flag_true_becomes_one_time_expense(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EXPENSE_ID_HEADER: "expense_car",
                            CATEGORY_HEADER: "車",
                            ONE_TIME_FLAG_HEADER: "TRUE",
                            EXPENSE_AMOUNT_HEADER: "3000000",
                            START_TYPE_HEADER: "age",
                            START_VALUE_HEADER: "45",
                        }
                    ]
                )
            }
        )

        expenses, one_time_expenses = _build_expenses(spreadsheet)

        self.assertEqual(expenses, [])
        self.assertEqual(len(one_time_expenses), 1)
        self.assertEqual(one_time_expenses[0].amount, Money.of(3_000_000))
        self.assertEqual(one_time_expenses[0].trigger.condition_type, EventConditionType.AGE)
        self.assertEqual(one_time_expenses[0].trigger.age, 45)

    def test_one_time_flag_true_without_start_type_raises_structural_input_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EXPENSE_ID_HEADER: "expense_car",
                            CATEGORY_HEADER: "車",
                            ONE_TIME_FLAG_HEADER: "TRUE",
                            EXPENSE_AMOUNT_HEADER: "3000000",
                        }
                    ]
                )
            }
        )

        with self.assertRaises(StructuralInputError) as ctx:
            _build_expenses(spreadsheet)
        self.assertEqual(ctx.exception.field_path, f"{EXPENSES_SHEET}!row2.{START_TYPE_HEADER}")


if __name__ == "__main__":
    unittest.main()
