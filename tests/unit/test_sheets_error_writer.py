import unittest

import gspread

from adapters.sheets.sheet_mapping import FIELD_PATH_HEADER, MESSAGE_HEADER, OUTPUT_ERRORS_SHEET, PLAN_SHEET
from adapters.sheets.sheets_error_writer import write_errors
from core.domain.errors import SemanticValidationError, StructuralInputError


class _FakeWorksheet:
    def __init__(self):
        self.updated_values = None
        self.cleared = False

    def clear(self):
        self.cleared = True

    def update(self, values, range_name):
        self.updated_values = values


class _FakeSpreadsheetExisting:
    def __init__(self, worksheet: _FakeWorksheet):
        self._worksheet = worksheet

    def worksheet(self, name):
        assert name == OUTPUT_ERRORS_SHEET
        return self._worksheet


class _FakeSpreadsheetMissing:
    def __init__(self):
        self.added_worksheet = None

    def worksheet(self, name):
        raise gspread.exceptions.WorksheetNotFound(name)

    def add_worksheet(self, title, rows, cols):
        self.added_worksheet = _FakeWorksheet()
        return self.added_worksheet


class WriteErrorsTest(unittest.TestCase):
    def test_writes_header_and_error_rows(self) -> None:
        worksheet = _FakeWorksheet()
        spreadsheet = _FakeSpreadsheetExisting(worksheet)
        errors = [
            StructuralInputError("必須項目が未入力です", f"{PLAN_SHEET}!生年月日"),
            SemanticValidationError("退職年齢が若すぎます", "milestones[m1].trigger.age"),
        ]

        write_errors(spreadsheet, errors)

        self.assertTrue(worksheet.cleared)
        self.assertEqual(
            worksheet.updated_values,
            [
                [FIELD_PATH_HEADER, MESSAGE_HEADER],
                [f"{PLAN_SHEET}!生年月日", "必須項目が未入力です"],
                ["milestones[m1].trigger.age", "退職年齢が若すぎます"],
            ],
        )

    def test_creates_sheet_when_missing(self) -> None:
        spreadsheet = _FakeSpreadsheetMissing()

        write_errors(spreadsheet, [])

        self.assertIsNotNone(spreadsheet.added_worksheet)
        self.assertEqual(spreadsheet.added_worksheet.updated_values, [[FIELD_PATH_HEADER, MESSAGE_HEADER]])


if __name__ == "__main__":
    unittest.main()
