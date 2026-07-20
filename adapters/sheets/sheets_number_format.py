"""金額(円)列にカンマ区切りの表示形式(#,##0)を設定する共通処理。

入力シート(sheets_formatting.py)・出力シート(sheets_output_adapter.py)の両方から使う。
「ヘッダー名/ラベル名がNON_MONEY_NUMERIC_LABELS（年齢・西暦年・月・比率等）に含まれない列・行は
既定ですべて金額とみなしてカンマ区切りにする」という方針にすることで、将来シートに列を追加した際も
個別の設定漏れが起きないようにする（sheets_formatting.pyの背景色分け「必須/任意を問わず、ヘッダーに
存在する列はすべて色を付ける」と同じ考え方）。数値ではない文字列セル（口座IDやカテゴリ等）に対しても
念のためこの表示形式を設定するが、Google Sheetsの表示形式は数値セルにしか影響しないため実害はない。
"""
from __future__ import annotations

from adapters.sheets.sheet_mapping import (
    AGE_HEADER,
    DASHBOARD_DEPLETION_AGE_LABEL,
    END_AGE_HEADER,
    END_VALUE_HEADER,
    EXPECTED_RETURN_HEADER,
    GROWTH_RATE_HEADER,
    INFLATION_RATE_HEADER,
    INVESTMENT_GROWTH_RATE_HEADER,
    METHOD_HEADER,
    MONTH_HEADER,
    PENSION_CLAIM_AGE_HEADER,
    RETIREMENT_AGE_HEADER,
    START_AGE_HEADER,
    START_VALUE_HEADER,
    TARGET_WEIGHT_HEADER,
    VOLATILITY_HEADER,
    YEAR_HEADER,
)

MONEY_NUMBER_FORMAT = {"type": "NUMBER", "pattern": "#,##0"}

# 数値ではあるが金額(円)ではない列・行（年齢・西暦年・月・比率等）。カンマ区切り表示の対象外とする。
# 開始/終了条件値(START_VALUE_HEADER/END_VALUE_HEADER)は年齢を表すことがある列のため、
# 金額として扱わないようここに含める(日付文字列のときは元々セルが数値ではないため実質無害だが、
# 明示的に除外しておく)。
NON_MONEY_NUMERIC_LABELS = {
    AGE_HEADER,
    START_AGE_HEADER,
    END_AGE_HEADER,
    RETIREMENT_AGE_HEADER,
    PENSION_CLAIM_AGE_HEADER,
    YEAR_HEADER,
    MONTH_HEADER,
    GROWTH_RATE_HEADER,
    INFLATION_RATE_HEADER,
    INVESTMENT_GROWTH_RATE_HEADER,
    EXPECTED_RETURN_HEADER,
    VOLATILITY_HEADER,
    TARGET_WEIGHT_HEADER,
    START_VALUE_HEADER,
    END_VALUE_HEADER,
    DASHBOARD_DEPLETION_AGE_LABEL,
    METHOD_HEADER,
}


def money_number_format_request(sheet_id: int, start_row: int, end_row: int, start_col: int, end_col: int) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {"userEnteredFormat": {"numberFormat": MONEY_NUMBER_FORMAT}},
            "fields": "userEnteredFormat.numberFormat",
        }
    }


def money_column_format_requests(sheet_id: int, header: list[str], start_row: int, end_row: int) -> list[dict]:
    """ヘッダー行付きテーブル用。ヘッダーがNON_MONEY_NUMERIC_LABELSに含まれない列すべてに、
    start_row〜end_row(0始まり、endは含まない)の範囲でカンマ区切りの表示形式を設定するリクエストを作る。
    """

    requests = []
    for col_idx, column_header in enumerate(header):
        if not column_header or column_header in NON_MONEY_NUMERIC_LABELS:
            continue
        requests.append(money_number_format_request(sheet_id, start_row, end_row, col_idx, col_idx + 1))
    return requests


def money_row_format_requests(sheet_id: int, row_labels: list[str], value_col: int = 1) -> list[dict]:
    """縦持ち(A列=ラベル/B列=値)シート用。ラベルがNON_MONEY_NUMERIC_LABELSに含まれない行の
    value_col列にカンマ区切りの表示形式を設定するリクエストを作る。
    """

    requests = []
    for row_idx, label in enumerate(row_labels):
        if not label or label in NON_MONEY_NUMERIC_LABELS:
            continue
        requests.append(money_number_format_request(sheet_id, row_idx, row_idx + 1, value_col, value_col + 1))
    return requests
