import unittest

import gspread

from adapters.sheets.sheet_mapping import (
    ERROR_KIND_LABEL,
    FIELD_PATH_HEADER,
    KIND_HEADER,
    MESSAGE_HEADER,
    OUTPUT_ERRORS_SHEET,
    PLAN_SHEET,
    WARNING_KIND_LABEL,
)
from adapters.sheets.sheets_error_writer import write_errors, write_warnings
from adapters.sheets.sheets_input_adapter import InputWarning
from core.domain.errors import SemanticValidationError, StructuralInputError


class _FakeWorksheet:
    def __init__(self):
        self.updated_values = None
        self.updates: list[tuple[list, str]] = []
        self.cleared = False

    def clear(self):
        self.cleared = True

    def update(self, values, range_name):
        self.updated_values = values
        self.updates.append((values, range_name))

    def get_all_values(self):
        return self.updated_values or []


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
                [KIND_HEADER, FIELD_PATH_HEADER, MESSAGE_HEADER],
                [ERROR_KIND_LABEL, f"{PLAN_SHEET}!生年月日", "必須項目が未入力です"],
                [ERROR_KIND_LABEL, "milestones[m1].trigger.age", "退職年齢が若すぎます"],
            ],
        )

    def test_creates_sheet_when_missing(self) -> None:
        spreadsheet = _FakeSpreadsheetMissing()

        write_errors(spreadsheet, [])

        self.assertIsNotNone(spreadsheet.added_worksheet)
        self.assertEqual(spreadsheet.added_worksheet.updated_values, [[KIND_HEADER, FIELD_PATH_HEADER, MESSAGE_HEADER]])


class WriteWarningsTest(unittest.TestCase):
    def test_appends_warning_rows_below_existing_content(self) -> None:
        worksheet = _FakeWorksheet()
        spreadsheet = _FakeSpreadsheetExisting(worksheet)
        write_errors(spreadsheet, [])  # 成功時にwrite_errorsがヘッダーのみ書き込んだ状態を再現
        warnings = [
            InputWarning("入力_支出!row2.成長率", "単発フラグ=TRUEの行では成長率は使われません（無視されます）"),
        ]

        write_warnings(spreadsheet, warnings)

        self.assertEqual(
            worksheet.updates[-1],
            (
                [[WARNING_KIND_LABEL, "入力_支出!row2.成長率", "単発フラグ=TRUEの行では成長率は使われません（無視されます）"]],
                "A2",
            ),
        )

    def test_does_nothing_when_no_warnings(self) -> None:
        worksheet = _FakeWorksheet()
        spreadsheet = _FakeSpreadsheetExisting(worksheet)
        write_errors(spreadsheet, [])
        update_count_before = len(worksheet.updates)

        write_warnings(spreadsheet, [])

        self.assertEqual(len(worksheet.updates), update_count_before)


if __name__ == "__main__":
    unittest.main()
