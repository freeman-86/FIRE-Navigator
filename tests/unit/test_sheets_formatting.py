import unittest

import gspread

from adapters.sheets import sheets_formatting
from adapters.sheets.sheet_mapping import (
    ACCOUNT_ID_HEADER,
    ACCOUNT_TYPE_HEADER,
    ACCOUNTS_SHEET,
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    BIRTH_DATE_HEADER,
    EXPECTED_RETURN_HEADER,
    MONTHLY_CONTRIBUTION_HEADER,
    OWNER_HEADER,
    PENSION_CLAIM_TIMING_HEADER,
    PLAN_ID_HEADER,
    PLAN_NAME_HEADER,
    PLAN_SHEET,
    RESIDENCE_HEADER,
    RETIREMENT_AGE_HEADER,
    VOLATILITY_HEADER,
)

EXAMPLES_SHEET = sheets_formatting.EXAMPLES_SHEET


class _FakeWorksheet:
    _next_id = 1

    def __init__(self, title: str, values=None):
        self.title = title
        self.id = _FakeWorksheet._next_id
        _FakeWorksheet._next_id += 1
        self._values = values or []
        self.cleared = False
        self.updates: list[tuple[list, str]] = []

    def row_values(self, row):
        idx = row - 1
        return self._values[idx] if idx < len(self._values) else []

    def col_values(self, col):
        idx = col - 1
        return [row[idx] for row in self._values if idx < len(row) and row[idx] != ""]

    def clear(self):
        self.cleared = True
        self._values = []
        self.updates = []

    def update(self, values, range_name):
        self.updates.append((values, range_name))
        self._values = values


class _FakeSpreadsheet:
    def __init__(self):
        self._worksheets: dict[str, _FakeWorksheet] = {}
        self.batch_updates: list[dict] = []

    def add_sheet(self, title: str, values=None) -> _FakeWorksheet:
        worksheet = _FakeWorksheet(title, values)
        self._worksheets[title] = worksheet
        return worksheet

    def worksheet(self, name):
        if name not in self._worksheets:
            raise gspread.exceptions.WorksheetNotFound(name)
        return self._worksheets[name]

    def add_worksheet(self, title, rows, cols, index=None):
        worksheet = _FakeWorksheet(title)
        self._worksheets[title] = worksheet
        return worksheet

    def batch_update(self, body):
        self.batch_updates.append(body)


def _asset_class_registry():
    return {"cash": "現金", "equity_sp500": "株式（S&P500連動）"}


class ApplyInputFormattingAccountsSheetTest(unittest.TestCase):
    def setUp(self):
        self.spreadsheet = _FakeSpreadsheet()
        header = [
            ACCOUNT_ID_HEADER,
            ACCOUNT_TYPE_HEADER,
            OWNER_HEADER,
            BALANCE_HEADER,
            ASSET_CLASS_HEADER,
            EXPECTED_RETURN_HEADER,
            VOLATILITY_HEADER,
            MONTHLY_CONTRIBUTION_HEADER,
        ]
        self.worksheet = self.spreadsheet.add_sheet(ACCOUNTS_SHEET, [header])

    def test_colors_required_columns_but_not_optional_column(self):
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        color_requests = [
            r["repeatCell"]
            for body in self.spreadsheet.batch_updates
            for r in body["requests"]
            if "repeatCell" in r and r["repeatCell"]["range"]["sheetId"] == self.worksheet.id
        ]
        single_column_requests = [r for r in color_requests if r["range"]["endColumnIndex"] - r["range"]["startColumnIndex"] == 1]
        colored_columns = {r["range"]["startColumnIndex"] for r in single_column_requests}

        required_columns = {0, 1, 2, 3, 4, 5, 6}  # ACCOUNT_ID..VOLATILITY (0-indexed)
        optional_column = 7  # MONTHLY_CONTRIBUTION_HEADER

        self.assertEqual(colored_columns, required_columns)
        self.assertNotIn(optional_column, colored_columns)

    def test_clears_previous_formatting_before_reapplying(self):
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        wide_clear_requests = [
            r["repeatCell"]
            for body in self.spreadsheet.batch_updates
            for r in body["requests"]
            if "repeatCell" in r
            and r["repeatCell"]["range"]["sheetId"] == self.worksheet.id
            and r["repeatCell"]["range"]["startColumnIndex"] == 0
            and r["repeatCell"]["range"]["endColumnIndex"] > 10
        ]
        self.assertTrue(wide_clear_requests, "sheet-wide clear request should run before per-column formatting")

        null_validation_clears = [
            r["setDataValidation"]
            for body in self.spreadsheet.batch_updates
            for r in body["requests"]
            if "setDataValidation" in r
            and r["setDataValidation"]["range"]["sheetId"] == self.worksheet.id
            and r["setDataValidation"]["rule"] is None
        ]
        self.assertTrue(null_validation_clears, "stale data validation rules should be cleared before reapplying")

    def test_adds_dropdown_validation_for_enum_columns(self):
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        validation_requests = [
            r["setDataValidation"]
            for body in self.spreadsheet.batch_updates
            for r in body["requests"]
            if "setDataValidation" in r
            and r["setDataValidation"]["range"]["sheetId"] == self.worksheet.id
            and r["setDataValidation"]["rule"] is not None
        ]
        by_column = {r["range"]["startColumnIndex"]: r for r in validation_requests}

        account_type_choices = {v["userEnteredValue"] for v in by_column[1]["rule"]["condition"]["values"]}
        owner_choices = {v["userEnteredValue"] for v in by_column[2]["rule"]["condition"]["values"]}
        asset_class_choices = {v["userEnteredValue"] for v in by_column[4]["rule"]["condition"]["values"]}

        self.assertEqual(account_type_choices, {"nisa_growth", "nisa_tsumitate", "ideco", "company_dc", "zaikei", "taxable", "cash"})
        self.assertEqual(owner_choices, {"self", "spouse", "joint"})
        self.assertEqual(asset_class_choices, {"cash", "equity_sp500"})
        self.assertTrue(by_column[1]["rule"]["strict"])


class ApplyInputFormattingPlanSheetTest(unittest.TestCase):
    def test_colors_required_keys_and_adds_dropdown_for_enum_keys(self):
        spreadsheet = _FakeSpreadsheet()
        rows = [
            [PLAN_ID_HEADER, "plan_001"],
            [PLAN_NAME_HEADER, "ベースプラン"],
            [BIRTH_DATE_HEADER, "1990-04-01"],
            [RESIDENCE_HEADER, "tokyo"],
            [RETIREMENT_AGE_HEADER, "60"],
            [PENSION_CLAIM_TIMING_HEADER, "standard"],
        ]
        worksheet = spreadsheet.add_sheet(PLAN_SHEET, rows)

        sheets_formatting.apply_input_formatting(spreadsheet, _asset_class_registry())

        color_requests = [
            r["repeatCell"]
            for body in spreadsheet.batch_updates
            for r in body["requests"]
            if "repeatCell" in r and r["repeatCell"]["range"]["sheetId"] == worksheet.id
        ]
        single_row_requests = [r for r in color_requests if r["range"]["endRowIndex"] - r["range"]["startRowIndex"] == 1]
        colored_rows = {r["range"]["startRowIndex"] for r in single_row_requests}

        # PLAN_ID(0), PLAN_NAME(1), BIRTH_DATE(2), RESIDENCE(3) are required; RETIREMENT_AGE(4) is not.
        self.assertEqual(colored_rows, {0, 1, 2, 3})

        validation_requests = [
            r["setDataValidation"]
            for body in spreadsheet.batch_updates
            for r in body["requests"]
            if "setDataValidation" in r
            and r["setDataValidation"]["range"]["sheetId"] == worksheet.id
            and r["setDataValidation"]["rule"] is not None
        ]
        validation_rows = {r["range"]["startRowIndex"] for r in validation_requests}
        self.assertEqual(validation_rows, {3, 5})  # RESIDENCE, PENSION_CLAIM_TIMING


class ApplyInputFormattingMissingOptionalSheetTest(unittest.TestCase):
    def test_skips_sheets_that_do_not_exist_without_error(self):
        spreadsheet = _FakeSpreadsheet()  # no sheets created at all

        sheets_formatting.apply_input_formatting(spreadsheet, _asset_class_registry())

        self.assertEqual(spreadsheet.batch_updates, [])


class WriteExamplesSheetTest(unittest.TestCase):
    def test_creates_examples_sheet_with_a_section_per_input_sheet(self):
        spreadsheet = _FakeSpreadsheet()

        sheets_formatting.write_examples_sheet(spreadsheet)

        worksheet = spreadsheet.worksheet(EXAMPLES_SHEET)
        values, range_name = worksheet.updates[0]
        self.assertEqual(range_name, "A1")

        flattened_first_cells = [row[0] for row in values if row]
        for sheet_name, _ in sheets_formatting._EXAMPLE_SECTIONS:
            self.assertIn(f"■ {sheet_name} の入力例", flattened_first_cells)

    def test_does_not_touch_real_input_sheets(self):
        spreadsheet = _FakeSpreadsheet()
        accounts_worksheet = spreadsheet.add_sheet(ACCOUNTS_SHEET, [[ACCOUNT_ID_HEADER], ["acc_real_001"]])

        sheets_formatting.write_examples_sheet(spreadsheet)

        self.assertEqual(accounts_worksheet.updates, [])
        self.assertFalse(accounts_worksheet.cleared)

    def test_rerunning_clears_previous_examples_sheet_instead_of_duplicating(self):
        spreadsheet = _FakeSpreadsheet()

        sheets_formatting.write_examples_sheet(spreadsheet)
        sheets_formatting.write_examples_sheet(spreadsheet)

        worksheet = spreadsheet.worksheet(EXAMPLES_SHEET)
        self.assertEqual(len(worksheet.updates), 1)  # 2回目のupdateだけが残る(clear->updateの繰り返し)


if __name__ == "__main__":
    unittest.main()
