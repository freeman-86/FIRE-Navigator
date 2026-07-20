"""入力シートの入力しやすさを改善する機能（必須/任意セルの色分け・チェックボックス・プルダウン・
条件付き書式・数値の右揃い・入力例）。

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
    COST_BASIS_HEADER,
    EDUCATION_BAND_ID_HEADER,
    EDUCATION_EXPENSES_SHEET,
    EMPLOYEE_PENSION_ESTIMATE_HEADER,
    END_AGE_HEADER,
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
    IS_FLEXIBLE_HEADER,
    MONTHLY_AMOUNT_HEADER,
    MONTHLY_CONTRIBUTION_HEADER,
    NATIONAL_PENSION_ESTIMATE_HEADER,
    ONE_TIME_AMOUNT_HEADER,
    ONE_TIME_FLAG_HEADER,
    OWNER_HEADER,
    PENSION_CLAIM_AGE_HEADER,
    PENSION_CLAIM_TIMING_HEADER,
    PLAN_ID_HEADER,
    PLAN_NAME_HEADER,
    PLAN_SHEET,
    PROGRESS_SHEET,
    RESIDENCE_HEADER,
    RETIREMENT_AGE_HEADER,
    SCENARIO_ID_HEADER,
    SCENARIO_NAME_HEADER,
    SCENARIOS_SHEET,
    SOURCE_HEADER,
    START_AGE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
    TARGET_ENDING_NETWORTH_HEADER,
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
# 任意セルの背景色（薄い青）。「入力欄ではあるが必須ではない」ことを示す
# （無色のままだと入力欄かどうか見分けがつかないため、必須/任意を問わずすべての入力列に色を付ける）。
OPTIONAL_CELL_COLOR = {"red": 0.878, "green": 0.929, "blue": 0.973}
# 単発フラグ=FALSEの行で使われない開始条件タイプ/値等をグレーアウトする際の背景色・文字色。
IGNORED_CELL_BACKGROUND_COLOR = {"red": 0.92, "green": 0.92, "blue": 0.92}
IGNORED_CELL_TEXT_COLOR = {"red": 0.6, "green": 0.6, "blue": 0.6}

# 背景色・プルダウンを適用する行数（ヘッダー行の次から）。将来の追加入力にも
# あらかじめ書式が効くよう、実データ行数より広めに確保する。
FORMAT_ROW_COUNT = 300

# 書式クリア対象の列数。列構成の変更（統合等）でヘッダーの位置がずれても、以前の実行で
# 別の列に付けた背景色・プルダウンが残らないよう、実際に使う列数より広めにクリアする
# （worksheet.clear()は値のみを消し、書式・データの入力規則は消さないため）。
FORMAT_CLEAR_COL_COUNT = 20
WHITE_CELL_COLOR = {"red": 1.0, "green": 1.0, "blue": 1.0}

CONDITION_TYPE_CHOICES = ["today", "plan_start", "age", "date"]

# 数値として保存すべき列（右揃い表示のため）。開始条件値/終了条件値はage(整数)とdate(文字列)の
# どちらもあり得るため、意図的にここへ含めない（誤って数値化すると日付文字列を壊すリスクがあるため）。
NUMERIC_HEADERS = {
    BALANCE_HEADER,
    COST_BASIS_HEADER,
    EXPECTED_RETURN_HEADER,
    VOLATILITY_HEADER,
    MONTHLY_CONTRIBUTION_HEADER,
    AMOUNT_ANNUAL_HEADER,
    ONE_TIME_AMOUNT_HEADER,
    START_AGE_HEADER,
    END_AGE_HEADER,
    MONTHLY_AMOUNT_HEADER,
    AGE_HEADER,
    TARGET_WEIGHT_HEADER,
    YEAR_HEADER,
    ACTUAL_NETWORTH_HEADER,
    RETIREMENT_AGE_HEADER,
    NATIONAL_PENSION_ESTIMATE_HEADER,
    EMPLOYEE_PENSION_ESTIMATE_HEADER,
    PENSION_CLAIM_AGE_HEADER,
    TARGET_ENDING_NETWORTH_HEADER,
    INFLATION_RATE_HEADER,
    INVESTMENT_GROWTH_RATE_HEADER,
}

# チェックボックスにする列（TRUE/FALSEの自由入力によるタイプミスを防ぐ）。
CHECKBOX_HEADERS = {ONE_TIME_FLAG_HEADER, IS_FLEXIBLE_HEADER}

# 列ヘッダーセルに付けるメモ（セルにマウスオーバーすると表示される補足説明）。
HEADER_NOTES: dict[str, dict[str, str]] = {
    INCOMES_SHEET: {
        END_TYPE_HEADER: "給与収入などがいつ止まるかはこちらで設定してください（today/plan_start/age/dateのいずれか）。",
        END_VALUE_HEADER: "給与収入などがいつ止まるかはこちらで設定してください（終了条件タイプに対応する値）。",
    },
}


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
            [INCOME_ID_HEADER, SOURCE_HEADER, AMOUNT_ANNUAL_HEADER, START_TYPE_HEADER, START_VALUE_HEADER],
            {START_TYPE_HEADER: CONDITION_TYPE_CHOICES, END_TYPE_HEADER: CONDITION_TYPE_CHOICES},
        ),
        TabularSheetSpec(
            EXPENSES_SHEET,
            [EXPENSE_ID_HEADER, CATEGORY_HEADER, ONE_TIME_FLAG_HEADER],
            {START_TYPE_HEADER: CONDITION_TYPE_CHOICES},
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


def _column_letter(index: int) -> str:
    """0始まりの列インデックスをA1表記の列名(A, B, ..., Z, AA, ...)に変換する。"""

    index += 1
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _repeat_cell_color_request(sheet_id: int, start_row: int, end_row: int, start_col: int, end_col: int, color: dict) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {"userEnteredFormat": {"backgroundColor": color}},
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


def _checkbox_request(sheet_id: int, start_row: int, end_row: int, start_col: int, end_col: int) -> dict:
    """TRUE/FALSEの自由入力の代わりにチェックボックスUIにする（insertCheckboxes）。
    既存のTRUE/FALSE文字列もチェック状態に変換される。
    """

    return {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True, "showCustomUi": True},
        }
    }


def _gray_out_when_one_time_flag_request(
    sheet_id: int, flag_col_idx: int, target_col_indices: list[int], flag_value: bool, rule_index: int
) -> dict:
    """単発フラグの値に応じて使われない（無視される）列を条件付き書式でグレーアウトする
    （ギャップ分析対応: 使われない入力欄を視覚的に示す）。target_col_indicesは連続していなくてもよい
    （列ごとに個別のrangeを作る）。
    """

    flag_col_letter = _column_letter(flag_col_idx)
    formula = f"=${flag_col_letter}2={'TRUE' if flag_value else 'FALSE'}"
    ranges = [
        {
            "sheetId": sheet_id,
            "startRowIndex": 1,
            "endRowIndex": FORMAT_ROW_COUNT,
            "startColumnIndex": col_idx,
            "endColumnIndex": col_idx + 1,
        }
        for col_idx in target_col_indices
    ]
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": ranges,
                "booleanRule": {
                    "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": formula}]},
                    "format": {
                        "backgroundColor": IGNORED_CELL_BACKGROUND_COLOR,
                        "textFormat": {"foregroundColor": IGNORED_CELL_TEXT_COLOR},
                    },
                },
            },
            "index": rule_index,
        }
    }


def _header_note_request(sheet_id: int, col_idx: int, note_text: str) -> dict:
    """列ヘッダーのセルにメモ（マウスオーバーで表示される補足説明）を設定する。列の値は変更しない。"""

    return {
        "updateCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": col_idx,
                "endColumnIndex": col_idx + 1,
            },
            "rows": [{"values": [{"note": note_text}]}],
            "fields": "note",
        }
    }


def _numeric_single_cell_request(sheet_id: int, row_idx: int, col_idx: int, raw: str) -> Optional[dict]:
    """1セル分の数値らしき文字列を、実際の数値(numberValue)として書き込み直すリクエストを作る
    （右揃い表示のため）。空欄・数値として解釈できない場合はNoneを返す（変更しない）。
    """

    raw = str(raw).strip()
    if raw == "":
        return None
    try:
        number = float(raw)
    except ValueError:
        return None
    return {
        "updateCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row_idx,
                "endRowIndex": row_idx + 1,
                "startColumnIndex": col_idx,
                "endColumnIndex": col_idx + 1,
            },
            "rows": [{"values": [{"userEnteredValue": {"numberValue": number}}]}],
            "fields": "userEnteredValue",
        }
    }


def _numeric_cell_requests(sheet_id: int, col_idx: int, data_values: list[str]) -> list[dict]:
    """列内の数値らしき文字列セルを、実際の数値(numberValue)として書き込み直すリクエストを作る
    （右揃い表示のため）。空欄・数値として解釈できないセルはそのまま変更しない。
    data_valuesはヘッダー行を除いたデータ行の値（先頭がシート上の2行目に対応）。
    """

    requests = []
    for row_offset, raw in enumerate(data_values, start=1):
        request = _numeric_single_cell_request(sheet_id, row_offset, col_idx, raw)
        if request is not None:
            requests.append(request)
    return requests


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


def _clear_conditional_format_requests(spreadsheet: gspread.Spreadsheet, sheet_id: int) -> list[dict]:
    metadata = spreadsheet.fetch_sheet_metadata()
    existing_rule_count = 0
    for sheet in metadata.get("sheets", []):
        if sheet["properties"]["sheetId"] == sheet_id:
            existing_rule_count = len(sheet.get("conditionalFormats", []))
            break
    # 削除するたびにindexが詰まるため、常にindex=0を指定すればよい。
    return [{"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}} for _ in range(existing_rule_count)]


def _tabular_sheet_requests(spreadsheet: gspread.Spreadsheet, spec: TabularSheetSpec) -> list[dict]:
    try:
        worksheet = spreadsheet.worksheet(spec.sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return []

    sheet_id = worksheet.id
    # updateCells(数値変換・チェックボックスの自動FALSE打ち消し)はグリッドの実際の行数を
    # 超える範囲を指定できない（repeatCell/setDataValidationと違い自動拡張されない）ため、
    # 先にグリッドをFORMAT_ROW_COUNT分まで広げておく。
    if worksheet.row_count < FORMAT_ROW_COUNT:
        worksheet.resize(rows=FORMAT_ROW_COUNT)

    values = worksheet.get_all_values()
    header = values[0] if values else []
    requests = _clear_range_requests(sheet_id, FORMAT_ROW_COUNT, FORMAT_CLEAR_COL_COUNT)
    requests.extend(_clear_conditional_format_requests(spreadsheet, sheet_id))

    data_row_count = max(len(values) - 1, 0)  # ヘッダーを除いた実データ行数
    first_future_row = 1 + data_row_count  # 0-indexed。この行以降はまだ実データがない
    notes_for_sheet = HEADER_NOTES.get(spec.sheet_name, {})

    # 必須/任意を問わず、ヘッダーに存在する列はすべて色を付ける（将来列が増えても漏れない）。
    for col_idx, column_header in enumerate(header):
        if not column_header:
            continue
        color = REQUIRED_CELL_COLOR if column_header in spec.required_headers else OPTIONAL_CELL_COLOR
        requests.append(_repeat_cell_color_request(sheet_id, 1, FORMAT_ROW_COUNT, col_idx, col_idx + 1, color))

        if column_header in notes_for_sheet:
            requests.append(_header_note_request(sheet_id, col_idx, notes_for_sheet[column_header]))

        if column_header in CHECKBOX_HEADERS:
            # チェックボックス(BOOLEAN型のデータの入力規則)には「未入力」の状態がなく、
            # 値のないセルにもGoogle Sheets側が自動的にFALSEを書き込んでしまう
            # （値だけ空に戻しても、入力規則が残っている限りFALSEに戻ってしまう）。
            # そのため他の列と違って実データ行より先には適用しない（get_all_records()が
            # 偽の空行を実データとして読み込んでしまうのを防ぐため）。新しく行を追加した後は
            # 再度セットアップを実行するとチェックボックスが効くようになる。
            if data_row_count > 0:
                requests.append(_checkbox_request(sheet_id, 1, first_future_row, col_idx, col_idx + 1))
        elif column_header in spec.dropdowns:
            requests.append(
                _data_validation_request(sheet_id, 1, FORMAT_ROW_COUNT, col_idx, col_idx + 1, spec.dropdowns[column_header])
            )

        if column_header in NUMERIC_HEADERS:
            data_values = [row[col_idx] if col_idx < len(row) else "" for row in values[1:]]
            requests.extend(_numeric_cell_requests(sheet_id, col_idx, data_values))

    # 入力_支出: 単発フラグの値に応じて使われない列をグレーアウトする。
    # FALSE(経常支出)の行では単発金額・開始条件タイプ/値が無視され、
    # TRUE(単発支出)の行では年間金額・成長率・柔軟支出フラグが無視される。
    if spec.sheet_name == EXPENSES_SHEET and ONE_TIME_FLAG_HEADER in header:
        flag_col_idx = header.index(ONE_TIME_FLAG_HEADER)
        unused_when_false = [h for h in (ONE_TIME_AMOUNT_HEADER, START_TYPE_HEADER, START_VALUE_HEADER) if h in header]
        unused_when_true = [h for h in (AMOUNT_ANNUAL_HEADER, GROWTH_RATE_HEADER, IS_FLEXIBLE_HEADER) if h in header]
        if unused_when_false:
            requests.append(
                _gray_out_when_one_time_flag_request(
                    sheet_id, flag_col_idx, [header.index(h) for h in unused_when_false], False, 0
                )
            )
        if unused_when_true:
            requests.append(
                _gray_out_when_one_time_flag_request(
                    sheet_id, flag_col_idx, [header.index(h) for h in unused_when_true], True, 1
                )
            )

    return requests


def _plan_sheet_requests(spreadsheet: gspread.Spreadsheet) -> list[dict]:
    try:
        worksheet = spreadsheet.worksheet(PLAN_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        return []

    sheet_id = worksheet.id
    rows = worksheet.get_all_values()
    requests = _clear_range_requests(sheet_id, FORMAT_ROW_COUNT, FORMAT_CLEAR_COL_COUNT)

    for row_idx, row in enumerate(rows):
        key = row[0] if row else ""
        if not key:
            continue
        color = REQUIRED_CELL_COLOR if key in PLAN_REQUIRED_KEYS else OPTIONAL_CELL_COLOR
        requests.append(_repeat_cell_color_request(sheet_id, row_idx, row_idx + 1, 1, 2, color))
        if key in PLAN_DROPDOWNS:
            requests.append(_data_validation_request(sheet_id, row_idx, row_idx + 1, 1, 2, PLAN_DROPDOWNS[key]))
        if key in NUMERIC_HEADERS:
            value = row[1] if len(row) > 1 else ""
            request = _numeric_single_cell_request(sheet_id, row_idx, 1, value)
            if request is not None:
                requests.append(request)

    return requests


def apply_input_formatting(
    spreadsheet: gspread.Spreadsheet, asset_class_registry: Optional[dict[AssetClass, str]] = None
) -> None:
    """全入力シートに、必須/任意セルの背景色・チェックボックス・プルダウン(データの入力規則)・
    条件付き書式・数値の右揃いを設定する。

    既存のセルの「実質的な値」は変更しない（数値らしき文字列を数値型として書き込み直す変換のみ、
    見た目上の値は変わらない）。存在しない入力シート（任意タブ）はスキップする。
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
