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
    CATEGORY_HEADER,
    EXPECTED_RETURN_HEADER,
    EXPENSE_AMOUNT_HEADER,
    EXPENSE_ID_HEADER,
    EXPENSES_SHEET,
    IS_FLEXIBLE_HEADER,
    MONTHLY_CONTRIBUTION_HEADER,
    ONE_TIME_FLAG_HEADER,
    OWNER_HEADER,
    PENSION_CLAIM_TIMING_HEADER,
    PLAN_ID_HEADER,
    PLAN_NAME_HEADER,
    PLAN_SHEET,
    RESIDENCE_HEADER,
    RETIREMENT_AGE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
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
        self.row_count = 10
        self.col_count = 10

    def row_values(self, row):
        idx = row - 1
        return self._values[idx] if idx < len(self._values) else []

    def col_values(self, col):
        idx = col - 1
        return [row[idx] for row in self._values if idx < len(row) and row[idx] != ""]

    def get_all_values(self):
        return self._values

    def resize(self, rows=None, cols=None):
        if rows is not None:
            self.row_count = rows
        if cols is not None:
            self.col_count = cols

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

    def fetch_sheet_metadata(self, params=None):
        return {
            "sheets": [
                {"properties": {"sheetId": ws.id}, "conditionalFormats": []} for ws in self._worksheets.values()
            ]
        }


def _asset_class_registry():
    return {"cash": "現金", "equity_sp500": "株式（S&P500連動）"}


def _color_requests(spreadsheet, sheet_id):
    return [
        r["repeatCell"]
        for body in spreadsheet.batch_updates
        for r in body["requests"]
        if "repeatCell" in r and r["repeatCell"]["range"]["sheetId"] == sheet_id
    ]


def _validation_requests(spreadsheet, sheet_id):
    return [
        r["setDataValidation"]
        for body in spreadsheet.batch_updates
        for r in body["requests"]
        if "setDataValidation" in r
        and r["setDataValidation"]["range"]["sheetId"] == sheet_id
        and r["setDataValidation"]["rule"] is not None
    ]


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
        data_row = ["acc_001", "cash", "self", "1000000", "cash", "0.05", "0.1", "30000"]
        self.worksheet = self.spreadsheet.add_sheet(ACCOUNTS_SHEET, [header, data_row])

    def test_colors_required_columns_yellow_and_optional_column_blue(self):
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        color_requests = _color_requests(self.spreadsheet, self.worksheet.id)
        single_column_requests = [
            r for r in color_requests if r["range"]["endColumnIndex"] - r["range"]["startColumnIndex"] == 1
        ]
        color_by_column = {
            r["range"]["startColumnIndex"]: r["cell"]["userEnteredFormat"]["backgroundColor"]
            for r in single_column_requests
        }

        required_columns = {0, 1, 2, 3, 4, 5, 6}  # ACCOUNT_ID..VOLATILITY (0-indexed)
        optional_column = 7  # MONTHLY_CONTRIBUTION_HEADER

        for col in required_columns:
            self.assertEqual(color_by_column[col], sheets_formatting.REQUIRED_CELL_COLOR)
        # 任意列も色が付く(無色のまま残らない)が、必須列とは異なる色になる
        self.assertEqual(color_by_column[optional_column], sheets_formatting.OPTIONAL_CELL_COLOR)
        self.assertNotEqual(sheets_formatting.OPTIONAL_CELL_COLOR, sheets_formatting.REQUIRED_CELL_COLOR)

    def test_clears_previous_formatting_before_reapplying(self):
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        wide_clear_requests = [
            r
            for r in _color_requests(self.spreadsheet, self.worksheet.id)
            if r["range"]["startColumnIndex"] == 0 and r["range"]["endColumnIndex"] > 10
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

        validation_requests = _validation_requests(self.spreadsheet, self.worksheet.id)
        by_column = {r["range"]["startColumnIndex"]: r for r in validation_requests}

        account_type_choices = {v["userEnteredValue"] for v in by_column[1]["rule"]["condition"]["values"]}
        owner_choices = {v["userEnteredValue"] for v in by_column[2]["rule"]["condition"]["values"]}
        asset_class_choices = {v["userEnteredValue"] for v in by_column[4]["rule"]["condition"]["values"]}

        self.assertEqual(account_type_choices, {"nisa_growth", "nisa_tsumitate", "ideco", "company_dc", "zaikei", "taxable", "cash"})
        self.assertEqual(owner_choices, {"self", "spouse", "joint"})
        self.assertEqual(asset_class_choices, {"cash", "equity_sp500"})
        self.assertTrue(by_column[1]["rule"]["strict"])
        self.assertEqual(by_column[1]["rule"]["condition"]["type"], "ONE_OF_LIST")

    def test_converts_numeric_looking_text_to_actual_numbers(self):
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        update_cells_requests = [
            r["updateCells"]
            for body in self.spreadsheet.batch_updates
            for r in body["requests"]
            if "updateCells" in r and r["updateCells"]["range"]["sheetId"] == self.worksheet.id
        ]
        by_column = {r["range"]["startColumnIndex"]: r for r in update_cells_requests}

        # BALANCE_HEADER(col3)="1000000" -> numberValue
        self.assertEqual(by_column[3]["rows"][0]["values"][0]["userEnteredValue"]["numberValue"], 1000000.0)
        # EXPECTED_RETURN_HEADER(col5)="0.05" -> numberValue
        self.assertEqual(by_column[5]["rows"][0]["values"][0]["userEnteredValue"]["numberValue"], 0.05)
        # ACCOUNT_ID_HEADER(col0, "acc_001")のような非数値列は対象外
        self.assertNotIn(0, by_column)
        # ACCOUNT_TYPE_HEADER(col1, "cash")も非数値
        self.assertNotIn(1, by_column)


class ApplyInputFormattingExpensesSheetTest(unittest.TestCase):
    def setUp(self):
        self.spreadsheet = _FakeSpreadsheet()
        header = [
            EXPENSE_ID_HEADER,
            CATEGORY_HEADER,
            ONE_TIME_FLAG_HEADER,
            EXPENSE_AMOUNT_HEADER,
            "成長率",
            IS_FLEXIBLE_HEADER,
            START_TYPE_HEADER,
            START_VALUE_HEADER,
        ]
        data_row = ["expense_001", "living", "FALSE", "3600000", "0.02", "FALSE", "", ""]
        self.worksheet = self.spreadsheet.add_sheet(EXPENSES_SHEET, [header, data_row])

    def test_one_time_flag_and_is_flexible_become_checkboxes(self):
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

        self.assertEqual(by_column[2]["rule"]["condition"]["type"], "BOOLEAN")  # 単発フラグ
        self.assertEqual(by_column[5]["rule"]["condition"]["type"], "BOOLEAN")  # 柔軟支出フラグ

    def test_checkbox_validation_is_scoped_to_existing_data_rows_only(self):
        # BOOLEAN型のデータの入力規則には「未入力」状態がなく、値のないセルにもGoogle Sheets側が
        # 自動でFALSEを書き込んでしまう(値だけを空に戻しても入力規則が残っていれば復活する)ため、
        # 他の列と違って実データ行(この場合1行)より先には適用しないことを確認する。
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

        for col in (2, 5):  # 単発フラグ, 柔軟支出フラグ
            self.assertEqual(by_column[col]["range"]["startRowIndex"], 1)
            self.assertEqual(by_column[col]["range"]["endRowIndex"], 2)  # 実データ1行分のみ

    def test_no_checkbox_validation_requested_when_sheet_has_no_data_rows(self):
        spreadsheet = _FakeSpreadsheet()
        header = [EXPENSE_ID_HEADER, CATEGORY_HEADER, ONE_TIME_FLAG_HEADER, EXPENSE_AMOUNT_HEADER, IS_FLEXIBLE_HEADER]
        worksheet = spreadsheet.add_sheet(EXPENSES_SHEET, [header])  # ヘッダーのみ、データ行なし

        sheets_formatting.apply_input_formatting(spreadsheet, _asset_class_registry())

        checkbox_requests = [
            r["setDataValidation"]
            for body in spreadsheet.batch_updates
            for r in body["requests"]
            if "setDataValidation" in r
            and r["setDataValidation"]["range"]["sheetId"] == worksheet.id
            and r["setDataValidation"]["rule"] is not None
            and r["setDataValidation"]["rule"]["condition"]["type"] == "BOOLEAN"
        ]
        self.assertEqual(checkbox_requests, [])

    def test_grays_out_start_condition_columns_when_one_time_flag_is_false(self):
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        conditional_rules = [
            r["addConditionalFormatRule"]["rule"]
            for body in self.spreadsheet.batch_updates
            for r in body["requests"]
            if "addConditionalFormatRule" in r
        ]
        self.assertEqual(len(conditional_rules), 1)
        rule = conditional_rules[0]
        formula = rule["booleanRule"]["condition"]["values"][0]["userEnteredValue"]
        self.assertIn("FALSE", formula)
        # 単発フラグ(col2)を参照している
        self.assertIn("C", formula)
        target_range = rule["ranges"][0]
        self.assertEqual(target_range["startColumnIndex"], 6)  # START_TYPE_HEADER
        self.assertEqual(target_range["endColumnIndex"], 8)  # START_VALUE_HEADERまで含む


class ApplyInputFormattingPlanSheetTest(unittest.TestCase):
    def test_colors_required_keys_yellow_and_optional_keys_blue(self):
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

        color_requests = _color_requests(spreadsheet, worksheet.id)
        single_row_requests = [r for r in color_requests if r["range"]["endRowIndex"] - r["range"]["startRowIndex"] == 1]
        color_by_row = {
            r["range"]["startRowIndex"]: r["cell"]["userEnteredFormat"]["backgroundColor"] for r in single_row_requests
        }

        # PLAN_ID(0), PLAN_NAME(1), BIRTH_DATE(2), RESIDENCE(3) are required; RETIREMENT_AGE(4)/PENSION_CLAIM_TIMING(5) are not.
        for row in (0, 1, 2, 3):
            self.assertEqual(color_by_row[row], sheets_formatting.REQUIRED_CELL_COLOR)
        for row in (4, 5):
            self.assertEqual(color_by_row[row], sheets_formatting.OPTIONAL_CELL_COLOR)

        validation_requests = _validation_requests(spreadsheet, worksheet.id)
        validation_rows = {r["range"]["startRowIndex"] for r in validation_requests}
        self.assertEqual(validation_rows, {3, 5})  # RESIDENCE, PENSION_CLAIM_TIMING

    def test_converts_numeric_plan_values_to_numbers(self):
        spreadsheet = _FakeSpreadsheet()
        rows = [
            [PLAN_ID_HEADER, "plan_001"],
            [RETIREMENT_AGE_HEADER, "60"],
        ]
        worksheet = spreadsheet.add_sheet(PLAN_SHEET, rows)

        sheets_formatting.apply_input_formatting(spreadsheet, _asset_class_registry())

        update_cells_requests = [
            r["updateCells"]
            for body in spreadsheet.batch_updates
            for r in body["requests"]
            if "updateCells" in r and r["updateCells"]["range"]["sheetId"] == worksheet.id
        ]
        self.assertEqual(len(update_cells_requests), 1)
        request = update_cells_requests[0]
        self.assertEqual(request["range"]["startRowIndex"], 1)  # RETIREMENT_AGE row
        self.assertEqual(request["rows"][0]["values"][0]["userEnteredValue"]["numberValue"], 60.0)


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
