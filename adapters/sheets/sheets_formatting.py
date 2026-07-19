"""入力シートの入力しやすさを改善する機能（必須セルの色分け・プルダウン・入力例）。

ユーザーフィードバック:
  3. 各入力シートで、実際に入力すべきセルに色をつけて分かりやすくする
  4. 各入力シートの近くに入力例（サンプル行）を貼り付ける
  5. 選択肢が決まっている列にプルダウン（データの入力規則）を設定し、無効な値を入力できないようにする

Point 4について: 入力例はget_all_records()で実データとして誤読されないよう、既存の入力シートとは
完全に別の「入力例」シートにまとめて書き出す（同じシートの余白列/余白行に置くと、gspreadの
get_all_records()がヘッダー行を各行の最大幅までパディングする際にヘッダー欄が重複扱いになり、
次回の入力読み込みが壊れる可能性があるため）。
"""
from __future__ import annotations

from typing import Optional

import gspread

from adapters.sheets.sample_data import (
    ACCOUNTS_ROWS,
    ALLOCATION_POLICY_ROWS,
    EDUCATION_EXPENSES_ROWS,
    EXPENSES_ROWS,
    INCOMES_ROWS,
    PLAN_ROWS,
    PROGRESS_ROWS,
    SCENARIOS_ROWS,
)
from adapters.sheets.sheet_mapping import (
    ACCOUNT_ID_HEADER,
    ACCOUNT_TYPE_HEADER,
    ACCOUNTS_SHEET,
    ACTUAL_NETWORTH_HEADER,
    AGE_HEADER,
    ALLOCATION_POLICY_SHEET,
    AMOUNT_ANNUAL_HEADER,
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    BIRTH_DATE_HEADER,
    CATEGORY_HEADER,
    CHILD_ID_HEADER,
    EDUCATION_BAND_ID_HEADER,
    EDUCATION_EXPENSES_SHEET,
    END_AGE_HEADER,
    END_TYPE_HEADER,
    EXPECTED_RETURN_HEADER,
    EXPENSE_AMOUNT_HEADER,
    EXPENSE_ID_HEADER,
    EXPENSES_SHEET,
    GROWTH_RATE_HEADER,
    INCOME_ID_HEADER,
    INCOMES_SHEET,
    INFLATION_RATE_HEADER,
    INVESTMENT_GROWTH_RATE_HEADER,
    IS_FLEXIBLE_HEADER,
    MONTHLY_AMOUNT_HEADER,
    ONE_TIME_FLAG_HEADER,
    OWNER_HEADER,
    PENSION_CLAIM_TIMING_HEADER,
    PLAN_ID_HEADER,
    PLAN_NAME_HEADER,
    PLAN_SHEET,
    PROGRESS_SHEET,
    RESIDENCE_HEADER,
    SCENARIO_ID_HEADER,
    SCENARIO_NAME_HEADER,
    SCENARIOS_SHEET,
    SOURCE_HEADER,
    START_AGE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
    TARGET_WEIGHT_HEADER,
    VOLATILITY_HEADER,
    YEAR_HEADER,
)
from core.domain.account import AccountType, OwnerType
from core.domain.asset import AssetClass
from core.domain.pension import ClaimTimingType
from core.domain.user import Prefecture
from repositories.asset_class_repository import load_asset_class_registry

EXAMPLES_SHEET = "入力例"

# 必須セルの背景色（薄い黄色）。既存の値そのものは変更しない、書式のみのハイライト。
REQUIRED_CELL_COLOR = {"red": 1.0, "green": 0.949, "blue": 0.702}

# 背景色・プルダウンを適用する行数（ヘッダー行の次から）。将来の追加入力にも
# あらかじめ書式が効くよう、実データ行数より広めに確保する。
FORMAT_ROW_COUNT = 300

# 書式クリア対象の列数。列構成の変更（統合等）でヘッダーの位置がずれても、以前の実行で
# 別の列に付けた背景色・プルダウンが残らないよう、実際に使う列数より広めにクリアする
# （worksheet.clear()は値のみを消し、書式・データの入力規則は消さないため）。
FORMAT_CLEAR_COL_COUNT = 20
WHITE_CELL_COLOR = {"red": 1.0, "green": 1.0, "blue": 1.0}

CONDITION_TYPE_CHOICES = ["today", "plan_start", "age", "date"]
BOOLEAN_CHOICES = ["TRUE", "FALSE"]


class TabularSheetSpec:
    def __init__(self, sheet_name: str, required_headers: list[str], dropdowns: Optional[dict[str, list[str]]] = None):
        self.sheet_name = sheet_name
        self.required_headers = required_headers
        self.dropdowns = dropdowns or {}


def _tabular_specs(asset_class_registry: dict[AssetClass, str]) -> list[TabularSheetSpec]:
    asset_classes = sorted(asset_class_registry.keys())
    return [
        TabularSheetSpec(
            ACCOUNTS_SHEET,
            [
                ACCOUNT_ID_HEADER,
                ACCOUNT_TYPE_HEADER,
                OWNER_HEADER,
                BALANCE_HEADER,
                ASSET_CLASS_HEADER,
                EXPECTED_RETURN_HEADER,
                VOLATILITY_HEADER,
            ],
            {
                ACCOUNT_TYPE_HEADER: [member.value for member in AccountType],
                OWNER_HEADER: [member.value for member in OwnerType],
                ASSET_CLASS_HEADER: asset_classes,
            },
        ),
        TabularSheetSpec(
            INCOMES_SHEET,
            [INCOME_ID_HEADER, SOURCE_HEADER, AMOUNT_ANNUAL_HEADER, GROWTH_RATE_HEADER, START_TYPE_HEADER, START_VALUE_HEADER],
            {START_TYPE_HEADER: CONDITION_TYPE_CHOICES, END_TYPE_HEADER: CONDITION_TYPE_CHOICES},
        ),
        TabularSheetSpec(
            EXPENSES_SHEET,
            [EXPENSE_ID_HEADER, CATEGORY_HEADER, ONE_TIME_FLAG_HEADER, EXPENSE_AMOUNT_HEADER],
            {IS_FLEXIBLE_HEADER: BOOLEAN_CHOICES, ONE_TIME_FLAG_HEADER: BOOLEAN_CHOICES, START_TYPE_HEADER: CONDITION_TYPE_CHOICES},
        ),
        TabularSheetSpec(SCENARIOS_SHEET, [SCENARIO_ID_HEADER, SCENARIO_NAME_HEADER]),
        TabularSheetSpec(PROGRESS_SHEET, [YEAR_HEADER, ACTUAL_NETWORTH_HEADER]),
        TabularSheetSpec(
            ALLOCATION_POLICY_SHEET,
            [AGE_HEADER, ASSET_CLASS_HEADER, TARGET_WEIGHT_HEADER],
            {ASSET_CLASS_HEADER: asset_classes},
        ),
        TabularSheetSpec(
            EDUCATION_EXPENSES_SHEET,
            [
                EDUCATION_BAND_ID_HEADER,
                CHILD_ID_HEADER,
                BIRTH_DATE_HEADER,
                CATEGORY_HEADER,
                START_AGE_HEADER,
                END_AGE_HEADER,
                MONTHLY_AMOUNT_HEADER,
            ],
        ),
    ]


PLAN_REQUIRED_KEYS = [
    PLAN_ID_HEADER,
    PLAN_NAME_HEADER,
    BIRTH_DATE_HEADER,
    RESIDENCE_HEADER,
    INFLATION_RATE_HEADER,
    INVESTMENT_GROWTH_RATE_HEADER,
]

PLAN_DROPDOWNS: dict[str, list[str]] = {
    RESIDENCE_HEADER: [member.value for member in Prefecture],
    PENSION_CLAIM_TIMING_HEADER: [member.value for member in ClaimTimingType],
}


def _repeat_cell_color_request(sheet_id: int, start_row: int, end_row: int, start_col: int, end_col: int) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {"userEnteredFormat": {"backgroundColor": REQUIRED_CELL_COLOR}},
            "fields": "userEnteredFormat.backgroundColor",
        }
    }


def _data_validation_request(
    sheet_id: int, start_row: int, end_row: int, start_col: int, end_col: int, choices: list[str]
) -> dict:
    return {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": choice} for choice in choices],
                },
                "strict": True,
                "showCustomUi": True,
            },
        }
    }


def _clear_range_requests(sheet_id: int, end_row: int, end_col: int) -> list[dict]:
    return [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": end_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": end_col,
                },
                "cell": {"userEnteredFormat": {"backgroundColor": WHITE_CELL_COLOR}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        },
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": end_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": end_col,
                },
                "rule": None,
            }
        },
    ]


def _tabular_sheet_requests(spreadsheet: gspread.Spreadsheet, spec: TabularSheetSpec) -> list[dict]:
    try:
        worksheet = spreadsheet.worksheet(spec.sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return []

    sheet_id = worksheet.id
    header = worksheet.row_values(1)
    requests = _clear_range_requests(sheet_id, FORMAT_ROW_COUNT, FORMAT_CLEAR_COL_COUNT)

    for column_header in spec.required_headers:
        if column_header not in header:
            continue
        col_idx = header.index(column_header)
        requests.append(_repeat_cell_color_request(sheet_id, 1, FORMAT_ROW_COUNT, col_idx, col_idx + 1))

    for column_header, choices in spec.dropdowns.items():
        if column_header not in header:
            continue
        col_idx = header.index(column_header)
        requests.append(_data_validation_request(sheet_id, 1, FORMAT_ROW_COUNT, col_idx, col_idx + 1, choices))

    return requests


def _plan_sheet_requests(spreadsheet: gspread.Spreadsheet) -> list[dict]:
    try:
        worksheet = spreadsheet.worksheet(PLAN_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        return []

    sheet_id = worksheet.id
    keys = worksheet.col_values(1)
    requests = _clear_range_requests(sheet_id, FORMAT_ROW_COUNT, FORMAT_CLEAR_COL_COUNT)

    for row_idx, key in enumerate(keys):
        if key in PLAN_REQUIRED_KEYS:
            requests.append(_repeat_cell_color_request(sheet_id, row_idx, row_idx + 1, 1, 2))
        if key in PLAN_DROPDOWNS:
            requests.append(_data_validation_request(sheet_id, row_idx, row_idx + 1, 1, 2, PLAN_DROPDOWNS[key]))

    return requests


def apply_input_formatting(
    spreadsheet: gspread.Spreadsheet, asset_class_registry: Optional[dict[AssetClass, str]] = None
) -> None:
    """全入力シートに、必須セルの背景色とプルダウン(データの入力規則)を設定する。

    既存のセルの値は一切変更しない（書式・入力規則のみ）。存在しない入力シート（任意タブ）は
    スキップする。
    """

    if asset_class_registry is None:
        asset_class_registry = load_asset_class_registry()

    requests: list[dict] = []
    requests.extend(_plan_sheet_requests(spreadsheet))
    for spec in _tabular_specs(asset_class_registry):
        requests.extend(_tabular_sheet_requests(spreadsheet, spec))

    if requests:
        spreadsheet.batch_update({"requests": requests})


# --- 入力例シート -----------------------------------------------------------------------------

_EXAMPLE_SECTIONS: list[tuple[str, list[list[str]]]] = [
    (PLAN_SHEET, PLAN_ROWS),
    (ACCOUNTS_SHEET, ACCOUNTS_ROWS),
    (INCOMES_SHEET, INCOMES_ROWS),
    (EXPENSES_SHEET, EXPENSES_ROWS),
    (SCENARIOS_SHEET, SCENARIOS_ROWS),
    (PROGRESS_SHEET, PROGRESS_ROWS),
    (ALLOCATION_POLICY_SHEET, ALLOCATION_POLICY_ROWS),
    (EDUCATION_EXPENSES_SHEET, EDUCATION_EXPENSES_ROWS),
]

_NOTE_TEXT = (
    "このシートは各「入力_◯◯」シートの記入例です。ここに書いた内容がシミュレーションに"
    "使われることはありません。書き方の参考にして、実際の値は各入力シートに記入してください。"
)


def _get_or_create_examples_worksheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    try:
        worksheet = spreadsheet.worksheet(EXAMPLES_SHEET)
        worksheet.clear()
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=EXAMPLES_SHEET, rows=200, cols=10, index=1)


def write_examples_sheet(spreadsheet: gspread.Spreadsheet) -> None:
    """全入力シートの入力例を1つの「入力例」シートにまとめて書き出す（既存入力シートは変更しない）。

    実データと混同されないよう、既存の入力シートとは完全に別のシートに書き出す（get_all_records()
    が読み込む範囲には一切含まれない）。
    """

    worksheet = _get_or_create_examples_worksheet(spreadsheet)

    values: list[list[str]] = [[_NOTE_TEXT], []]
    title_rows: list[int] = []
    header_rows: list[int] = []

    for sheet_name, rows in _EXAMPLE_SECTIONS:
        title_rows.append(len(values))
        values.append([f"■ {sheet_name} の入力例"])
        header_rows.append(len(values))
        values.extend(rows)
        values.append([])

    worksheet.update(values=values, range_name="A1")

    sheet_id = worksheet.id
    requests = [
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"italic": True}}},
                "fields": "userEnteredFormat.textFormat.italic",
            }
        }
    ]
    for row in title_rows:
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row,
                        "endRowIndex": row + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                    "fields": "userEnteredFormat.textFormat.bold",
                }
            }
        )
    for row in header_rows:
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row,
                        "endRowIndex": row + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 10,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                        }
                    },
                    "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor",
                }
            }
        )

    spreadsheet.batch_update({"requests": requests})
