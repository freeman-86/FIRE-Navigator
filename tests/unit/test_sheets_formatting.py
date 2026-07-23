import unittest

import gspread

from adapters.sheets import sheets_formatting
from adapters.sheets.sheet_mapping import (
    ACCOUNT_ID_HEADER,
    ACCOUNT_TYPE_HEADER,
    ACCOUNTS_SHEET,
    AMOUNT_ANNUAL_HEADER,
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    BIRTH_DATE_HEADER,
    CATEGORY_HEADER,
    END_TYPE_HEADER,
    END_VALUE_HEADER,
    EXPECTED_RETURN_HEADER,
    EXPENSE_ID_HEADER,
    EXPENSES_SHEET,
    GROWTH_RATE_HEADER,
    INCOME_ID_HEADER,
    INCOMES_SHEET,
    INFLATION_RATE_HEADER,
    INVESTMENT_GROWTH_RATE_HEADER,
    MONTHLY_CONTRIBUTION_HEADER,
    ONE_TIME_AMOUNT_HEADER,
    ONE_TIME_FLAG_HEADER,
    OUTPUT_DASHBOARD_SHEET,
    PENSION_CLAIM_TIMING_HEADER,
    PLAN_ID_HEADER,
    PLAN_NAME_HEADER,
    PLAN_SHEET,
    PROGRESS_SHEET,
    RETIREMENT_AGE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
    TARGET_ENDING_NETWORTH_HEADER,
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
        if "repeatCell" in r
        and r["repeatCell"]["range"]["sheetId"] == sheet_id
        and r["repeatCell"]["fields"] == "userEnteredFormat.backgroundColor"
    ]


def _number_format_requests(spreadsheet, sheet_id):
    return [
        r["repeatCell"]
        for body in spreadsheet.batch_updates
        for r in body["requests"]
        if "repeatCell" in r
        and r["repeatCell"]["range"]["sheetId"] == sheet_id
        and r["repeatCell"]["fields"] == "userEnteredFormat.numberFormat"
        and r["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"]["type"] == "NUMBER"
    ]


def _percent_format_requests(spreadsheet, sheet_id):
    return [
        r["repeatCell"]
        for body in spreadsheet.batch_updates
        for r in body["requests"]
        if "repeatCell" in r
        and r["repeatCell"]["range"]["sheetId"] == sheet_id
        and r["repeatCell"]["fields"] == "userEnteredFormat.numberFormat"
        and r["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"]["type"] == "PERCENT"
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
            BALANCE_HEADER,
            ASSET_CLASS_HEADER,
            EXPECTED_RETURN_HEADER,
            MONTHLY_CONTRIBUTION_HEADER,
        ]
        data_row = ["acc_001", "cash", "1000000", "cash", "0.05", "30000"]
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

        required_columns = {0, 1, 3, 4}  # ACCOUNT_ID, ACCOUNT_TYPE, ASSET_CLASS, EXPECTED_RETURN (0-indexed)
        optional_columns = {2, 5}  # BALANCE_HEADER(空欄は0円扱い), MONTHLY_CONTRIBUTION_HEADER

        for col in required_columns:
            self.assertEqual(color_by_column[col], sheets_formatting.REQUIRED_CELL_COLOR)
        # 任意列も色が付く(無色のまま残らない)が、必須列とは異なる色になる
        for col in optional_columns:
            self.assertEqual(color_by_column[col], sheets_formatting.OPTIONAL_CELL_COLOR)
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
        asset_class_choices = {v["userEnteredValue"] for v in by_column[3]["rule"]["condition"]["values"]}

        self.assertEqual(account_type_choices, {"nisa_growth", "nisa_tsumitate", "ideco", "company_dc", "zaikei", "taxable", "cash"})
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

        # BALANCE_HEADER(col2)="1000000" -> numberValue
        self.assertEqual(by_column[2]["rows"][0]["values"][0]["userEnteredValue"]["numberValue"], 1000000.0)
        # EXPECTED_RETURN_HEADER(col4)="0.05" -> numberValue
        self.assertEqual(by_column[4]["rows"][0]["values"][0]["userEnteredValue"]["numberValue"], 0.05)
        # ACCOUNT_ID_HEADER(col0, "acc_001")のような非数値列は対象外
        self.assertNotIn(0, by_column)
        # ACCOUNT_TYPE_HEADER(col1, "cash")も非数値
        self.assertNotIn(1, by_column)

    def test_money_columns_get_comma_number_format_but_rate_columns_do_not(self):
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        number_format_requests = _number_format_requests(self.spreadsheet, self.worksheet.id)
        formatted_columns = {r["range"]["startColumnIndex"] for r in number_format_requests}

        self.assertIn(2, formatted_columns)  # BALANCE_HEADER(残高)
        self.assertIn(5, formatted_columns)  # MONTHLY_CONTRIBUTION_HEADER(月次拠出額)
        self.assertNotIn(4, formatted_columns)  # EXPECTED_RETURN_HEADER(期待リターン、比率)
        # 将来の追加行にも適用されるよう、実データ行数を超えて広めに設定する
        balance_request = next(r for r in number_format_requests if r["range"]["startColumnIndex"] == 2)
        self.assertGreater(balance_request["range"]["endRowIndex"], 2)

    def test_rate_columns_get_percent_number_format_but_money_columns_do_not(self):
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        percent_format_requests = _percent_format_requests(self.spreadsheet, self.worksheet.id)
        formatted_columns = {r["range"]["startColumnIndex"] for r in percent_format_requests}

        self.assertEqual(formatted_columns, {4})  # EXPECTED_RETURN_HEADER
        # 将来の追加行にも適用されるよう、実データ行数を超えて広めに設定する
        expected_return_request = next(r for r in percent_format_requests if r["range"]["startColumnIndex"] == 4)
        self.assertGreater(expected_return_request["range"]["endRowIndex"], 2)


class ApplyInputFormattingIncomesSheetTest(unittest.TestCase):
    def test_adds_note_explaining_end_condition_columns(self):
        spreadsheet = _FakeSpreadsheet()
        header = [
            INCOME_ID_HEADER,
            "収入源",
            AMOUNT_ANNUAL_HEADER,
            START_TYPE_HEADER,
            START_VALUE_HEADER,
            END_TYPE_HEADER,
            END_VALUE_HEADER,
        ]
        worksheet = spreadsheet.add_sheet(INCOMES_SHEET, [header])

        sheets_formatting.apply_input_formatting(spreadsheet, _asset_class_registry())

        note_requests = [
            r["updateCells"]
            for body in spreadsheet.batch_updates
            for r in body["requests"]
            if "updateCells" in r
            and r["updateCells"]["range"]["sheetId"] == worksheet.id
            and r["updateCells"].get("fields") == "note"
        ]
        by_column = {r["range"]["startColumnIndex"]: r for r in note_requests}

        self.assertIn(5, by_column)  # END_TYPE_HEADER
        self.assertIn(6, by_column)  # END_VALUE_HEADER
        for col in (5, 6):
            note = by_column[col]["rows"][0]["values"][0]["note"]
            self.assertIn("給与収入", note)
        # ヘッダー行(row0)のみが対象
        self.assertTrue(all(r["range"]["startRowIndex"] == 0 for r in by_column.values()))
        # 開始条件タイプ列にはメモを付けない
        self.assertNotIn(3, by_column)


class ApplyInputFormattingExpensesSheetTest(unittest.TestCase):
    def setUp(self):
        self.spreadsheet = _FakeSpreadsheet()
        header = [
            EXPENSE_ID_HEADER,
            CATEGORY_HEADER,
            ONE_TIME_FLAG_HEADER,
            AMOUNT_ANNUAL_HEADER,
            ONE_TIME_AMOUNT_HEADER,
            GROWTH_RATE_HEADER,
            START_TYPE_HEADER,
            START_VALUE_HEADER,
        ]
        data_row = ["expense_001", "living", "FALSE", "3600000", "", "0.02", "", ""]
        self.worksheet = self.spreadsheet.add_sheet(EXPENSES_SHEET, [header, data_row])

    def test_one_time_flag_becomes_checkbox(self):
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

    def test_existing_checkbox_column_values_are_rewritten_as_actual_booleans(self):
        # BOOLEAN型の入力規則を設定しても、既存の文字列"TRUE"/"FALSE"が自動でbooleanに変換される
        # とは限らないため、明示的にboolValueとして書き込み直すことを確認する。
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        bool_requests = [
            r["updateCells"]
            for body in self.spreadsheet.batch_updates
            for r in body["requests"]
            if "updateCells" in r
            and r["updateCells"]["range"]["sheetId"] == self.worksheet.id
            and r["updateCells"]["rows"][0]["values"][0].get("userEnteredValue", {}).get("boolValue") is not None
        ]
        by_column = {r["range"]["startColumnIndex"]: r for r in bool_requests}

        self.assertIn(2, by_column)  # 単発フラグ
        self.assertEqual(by_column[2]["rows"][0]["values"][0]["userEnteredValue"]["boolValue"], False)

    def test_start_value_is_converted_to_number_only_when_start_type_is_age(self):
        spreadsheet = _FakeSpreadsheet()
        header = [
            EXPENSE_ID_HEADER,
            CATEGORY_HEADER,
            ONE_TIME_FLAG_HEADER,
            AMOUNT_ANNUAL_HEADER,
            ONE_TIME_AMOUNT_HEADER,
            GROWTH_RATE_HEADER,
            START_TYPE_HEADER,
            START_VALUE_HEADER,
        ]
        age_row = ["expense_car", "車", "TRUE", "", "3000000", "", "age", "45"]
        date_row = ["expense_trip", "旅行", "TRUE", "", "500000", "", "date", "2030-05-01"]
        worksheet = spreadsheet.add_sheet(EXPENSES_SHEET, [header, age_row, date_row])

        sheets_formatting.apply_input_formatting(spreadsheet, _asset_class_registry())

        numeric_requests = [
            r["updateCells"]
            for body in spreadsheet.batch_updates
            for r in body["requests"]
            if "updateCells" in r
            and r["updateCells"]["range"]["sheetId"] == worksheet.id
            and r["updateCells"]["range"]["startColumnIndex"] == 7  # START_VALUE_HEADER
        ]
        by_row = {r["range"]["startRowIndex"]: r for r in numeric_requests}

        self.assertIn(1, by_row)  # age行は数値変換される
        self.assertEqual(by_row[1]["rows"][0]["values"][0]["userEnteredValue"]["numberValue"], 45.0)
        self.assertNotIn(2, by_row)  # date行は文字列のまま(数値変換しない)

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

        for col in (2,):  # 単発フラグ
            self.assertEqual(by_column[col]["range"]["startRowIndex"], 1)
            self.assertEqual(by_column[col]["range"]["endRowIndex"], 2)  # 実データ1行分のみ

    def test_no_checkbox_validation_requested_when_sheet_has_no_data_rows(self):
        spreadsheet = _FakeSpreadsheet()
        header = [
            EXPENSE_ID_HEADER,
            CATEGORY_HEADER,
            ONE_TIME_FLAG_HEADER,
            AMOUNT_ANNUAL_HEADER,
            ONE_TIME_AMOUNT_HEADER,
        ]
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

    def test_grays_out_columns_unused_for_the_current_one_time_flag_value(self):
        sheets_formatting.apply_input_formatting(self.spreadsheet, _asset_class_registry())

        conditional_rules = [
            r["addConditionalFormatRule"]["rule"]
            for body in self.spreadsheet.batch_updates
            for r in body["requests"]
            if "addConditionalFormatRule" in r
        ]
        self.assertEqual(len(conditional_rules), 2)

        rules_by_formula_flag = {}
        for rule in conditional_rules:
            formula = rule["booleanRule"]["condition"]["values"][0]["userEnteredValue"]
            self.assertIn("C", formula)  # 単発フラグ(col2)を参照している
            flag_value = "TRUE" if "TRUE" in formula else "FALSE"
            rules_by_formula_flag[flag_value] = rule

        # FALSE(経常支出)の行では単発金額・開始条件タイプ/値が無視される
        false_columns = {r["startColumnIndex"] for r in rules_by_formula_flag["FALSE"]["ranges"]}
        self.assertEqual(false_columns, {4, 6, 7})  # ONE_TIME_AMOUNT, START_TYPE, START_VALUE

        # TRUE(単発支出)の行では年間金額・成長率が無視される
        true_columns = {r["startColumnIndex"] for r in rules_by_formula_flag["TRUE"]["ranges"]}
        self.assertEqual(true_columns, {3, 5})  # AMOUNT_ANNUAL, GROWTH_RATE


class ApplyInputFormattingPlanSheetTest(unittest.TestCase):
    def test_colors_required_keys_yellow_and_optional_keys_blue(self):
        spreadsheet = _FakeSpreadsheet()
        rows = [
            [PLAN_ID_HEADER, "plan_001"],
            [PLAN_NAME_HEADER, "ベースプラン"],
            [BIRTH_DATE_HEADER, "1990-04-01"],
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

        # PLAN_ID(0), PLAN_NAME(1), BIRTH_DATE(2) are required; RETIREMENT_AGE(3)/PENSION_CLAIM_TIMING(4) are not.
        for row in (0, 1, 2):
            self.assertEqual(color_by_row[row], sheets_formatting.REQUIRED_CELL_COLOR)
        for row in (3, 4):
            self.assertEqual(color_by_row[row], sheets_formatting.OPTIONAL_CELL_COLOR)

        validation_requests = _validation_requests(spreadsheet, worksheet.id)
        validation_rows = {r["range"]["startRowIndex"] for r in validation_requests}
        self.assertEqual(validation_rows, {4})  # PENSION_CLAIM_TIMING

    def test_money_rows_get_comma_number_format_but_age_row_does_not(self):
        spreadsheet = _FakeSpreadsheet()
        rows = [
            [PLAN_ID_HEADER, "plan_001"],
            [TARGET_ENDING_NETWORTH_HEADER, "20000000"],
            [RETIREMENT_AGE_HEADER, "60"],
        ]
        worksheet = spreadsheet.add_sheet(PLAN_SHEET, rows)

        sheets_formatting.apply_input_formatting(spreadsheet, _asset_class_registry())

        number_format_requests = _number_format_requests(spreadsheet, worksheet.id)
        formatted_rows = {r["range"]["startRowIndex"] for r in number_format_requests}

        self.assertIn(1, formatted_rows)  # TARGET_ENDING_NETWORTH_HEADER(目標資産)
        self.assertNotIn(2, formatted_rows)  # RETIREMENT_AGE_HEADER(年齢)

    def test_rate_rows_get_percent_number_format(self):
        spreadsheet = _FakeSpreadsheet()
        rows = [
            [PLAN_ID_HEADER, "plan_001"],
            [INFLATION_RATE_HEADER, "0.02"],
            [INVESTMENT_GROWTH_RATE_HEADER, "0.05"],
            [RETIREMENT_AGE_HEADER, "60"],
        ]
        worksheet = spreadsheet.add_sheet(PLAN_SHEET, rows)

        sheets_formatting.apply_input_formatting(spreadsheet, _asset_class_registry())

        percent_format_requests = _percent_format_requests(spreadsheet, worksheet.id)
        formatted_rows = {r["range"]["startRowIndex"] for r in percent_format_requests}

        self.assertEqual(formatted_rows, {1, 2})  # INFLATION_RATE_HEADER, INVESTMENT_GROWTH_RATE_HEADER

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


class OrganizeSheetTabsTest(unittest.TestCase):
    def test_orders_present_sheets_and_skips_missing_ones(self):
        spreadsheet = _FakeSpreadsheet()
        # わざと逆順・バラバラに作成し、TAB_LAYOUT通りに並べ替えられることを確認する。
        # ACCOUNTS_SHEET等の中間シートはあえて作らず、存在しないシートがスキップされることも確認する。
        ws_dashboard = spreadsheet.add_sheet(OUTPUT_DASHBOARD_SHEET)
        ws_progress = spreadsheet.add_sheet(PROGRESS_SHEET)
        ws_expenses = spreadsheet.add_sheet(EXPENSES_SHEET)
        ws_plan = spreadsheet.add_sheet(PLAN_SHEET)

        sheets_formatting.organize_sheet_tabs(spreadsheet)

        requests = [r["updateSheetProperties"] for body in spreadsheet.batch_updates for r in body["requests"]]
        index_by_sheet_id = {r["properties"]["sheetId"]: r["properties"]["index"] for r in requests}
        color_by_sheet_id = {r["properties"]["sheetId"]: r["properties"]["tabColor"] for r in requests}

        # プラン設定(頻繁)→支出(頻繁)→実績(たまに)→ダッシュボード(出力)の順
        self.assertLess(index_by_sheet_id[ws_plan.id], index_by_sheet_id[ws_expenses.id])
        self.assertLess(index_by_sheet_id[ws_expenses.id], index_by_sheet_id[ws_progress.id])
        self.assertLess(index_by_sheet_id[ws_progress.id], index_by_sheet_id[ws_dashboard.id])
        self.assertEqual(color_by_sheet_id[ws_plan.id], sheets_formatting.FREQUENT_INPUT_TAB_COLOR)
        self.assertEqual(color_by_sheet_id[ws_expenses.id], sheets_formatting.FREQUENT_INPUT_TAB_COLOR)
        self.assertEqual(color_by_sheet_id[ws_progress.id], sheets_formatting.OCCASIONAL_INPUT_TAB_COLOR)
        self.assertEqual(color_by_sheet_id[ws_dashboard.id], sheets_formatting.OUTPUT_TAB_COLOR)

    def test_does_nothing_when_no_known_sheets_exist(self):
        spreadsheet = _FakeSpreadsheet()

        sheets_formatting.organize_sheet_tabs(spreadsheet)

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

    def test_applies_percent_format_to_rate_cells_in_both_vertical_and_tabular_sections(self):
        spreadsheet = _FakeSpreadsheet()

        sheets_formatting.write_examples_sheet(spreadsheet)

        worksheet = spreadsheet.worksheet(EXAMPLES_SHEET)
        values = worksheet.updates[0][0]
        percent_requests = _percent_format_requests(spreadsheet, worksheet.id)
        formatted_cells = {(r["range"]["startRowIndex"], r["range"]["startColumnIndex"]) for r in percent_requests}

        # 入力_プラン設定セクション(縦持ち: A列=キー/B列=値): インフレ率の行のB列(index1)が対象
        inflation_row = next(i for i, row in enumerate(values) if row and row[0] == INFLATION_RATE_HEADER)
        self.assertIn((inflation_row, 1), formatted_cells)

        # 入力_口座セクション(横持ち: ヘッダー行+データ行): 期待リターン列が対象
        accounts_title_row = values.index([f"■ {ACCOUNTS_SHEET} の入力例"])
        accounts_header_row = accounts_title_row + 1
        expected_return_col = values[accounts_header_row].index(EXPECTED_RETURN_HEADER)
        self.assertIn((accounts_header_row + 1, expected_return_col), formatted_cells)


if __name__ == "__main__":
    unittest.main()
