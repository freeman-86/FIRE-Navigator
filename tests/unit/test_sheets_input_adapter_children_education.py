import unittest
from datetime import date

import gspread

from adapters.sheets.sheet_mapping import (
    BIRTH_DATE_HEADER,
    CATEGORY_HEADER,
    CHILD_ID_HEADER,
    CHILDREN_SHEET,
    EDUCATION_BAND_ID_HEADER,
    EDUCATION_EXPENSES_SHEET,
    END_AGE_HEADER,
    EXPENSE_ID_HEADER,
    MONTHLY_AMOUNT_HEADER,
    ONE_TIME_AMOUNT_HEADER,
    ONE_TIME_EXPENSES_SHEET,
    START_AGE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
)
from adapters.sheets.sheets_input_adapter import (
    _build_children,
    _build_education_expenses,
    _build_one_time_expenses,
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


class BuildChildrenTest(unittest.TestCase):
    def test_missing_sheet_returns_empty_list(self) -> None:
        self.assertEqual(_build_children(_FakeSpreadsheet({})), [])

    def test_reads_children(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                CHILDREN_SHEET: _FakeWorksheet(
                    records=[{CHILD_ID_HEADER: "child_001", BIRTH_DATE_HEADER: "2020-04-01"}]
                )
            }
        )

        children = _build_children(spreadsheet)

        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].child_id, "child_001")
        self.assertEqual(children[0].birth_date, date(2020, 4, 1))


class BuildEducationExpensesTest(unittest.TestCase):
    def test_missing_sheet_returns_empty_list(self) -> None:
        self.assertEqual(_build_education_expenses(_FakeSpreadsheet({})), [])

    def test_reads_bands(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                EDUCATION_EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EDUCATION_BAND_ID_HEADER: "band_001",
                            CHILD_ID_HEADER: "child_001",
                            CATEGORY_HEADER: "小学校",
                            START_AGE_HEADER: "6",
                            END_AGE_HEADER: "11",
                            MONTHLY_AMOUNT_HEADER: "20000",
                        }
                    ]
                )
            }
        )

        bands = _build_education_expenses(spreadsheet)

        self.assertEqual(len(bands), 1)
        self.assertEqual(bands[0].child_id, "child_001")
        self.assertEqual(bands[0].start_age, 6)
        self.assertEqual(bands[0].end_age, 11)
        self.assertEqual(bands[0].monthly_amount, Money.of(20_000))


class BuildOneTimeExpensesTest(unittest.TestCase):
    def test_missing_sheet_returns_empty_list(self) -> None:
        self.assertEqual(_build_one_time_expenses(_FakeSpreadsheet({})), [])

    def test_reads_age_triggered_expense(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                ONE_TIME_EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EXPENSE_ID_HEADER: "expense_car",
                            CATEGORY_HEADER: "車",
                            ONE_TIME_AMOUNT_HEADER: "3000000",
                            START_TYPE_HEADER: "age",
                            START_VALUE_HEADER: "45",
                        }
                    ]
                )
            }
        )

        expenses = _build_one_time_expenses(spreadsheet)

        self.assertEqual(len(expenses), 1)
        self.assertEqual(expenses[0].amount, Money.of(3_000_000))
        self.assertEqual(expenses[0].trigger.condition_type, EventConditionType.AGE)
        self.assertEqual(expenses[0].trigger.age, 45)

    def test_missing_trigger_type_raises_structural_input_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                ONE_TIME_EXPENSES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            EXPENSE_ID_HEADER: "expense_car",
                            CATEGORY_HEADER: "車",
                            ONE_TIME_AMOUNT_HEADER: "3000000",
                        }
                    ]
                )
            }
        )

        with self.assertRaises(StructuralInputError) as ctx:
            _build_one_time_expenses(spreadsheet)
        self.assertEqual(ctx.exception.field_path, f"{ONE_TIME_EXPENSES_SHEET}!row2.{START_TYPE_HEADER}")


if __name__ == "__main__":
    unittest.main()
