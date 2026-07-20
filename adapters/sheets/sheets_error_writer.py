from __future__ import annotations

import gspread

from adapters.sheets.sheet_mapping import (
    ERROR_KIND_LABEL,
    FIELD_PATH_HEADER,
    KIND_HEADER,
    MESSAGE_HEADER,
    OUTPUT_ERRORS_SHEET,
    WARNING_KIND_LABEL,
)
from adapters.sheets.sheets_input_adapter import InputWarning
from core.domain.errors import FireNavigatorError

_HEADER_ROW = [KIND_HEADER, FIELD_PATH_HEADER, MESSAGE_HEADER]


def write_errors(spreadsheet: gspread.Spreadsheet, errors: list[FireNavigatorError]) -> None:
    """検出されたエラーを出力_エラーシートへ「どのフィールドで・何が」の形で一覧表示する
    （設計書11.2〜11.3。例外を握りつぶさず、直すべき場所まで含めて返す）。

    シート全体をクリアしてから書き込むため、警告(write_warnings)より先に呼び出すこと。
    """

    rows: list[list[object]] = [_HEADER_ROW]
    rows += [[ERROR_KIND_LABEL, error.field_path, error.message] for error in errors]

    try:
        worksheet = spreadsheet.worksheet(OUTPUT_ERRORS_SHEET)
        worksheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=OUTPUT_ERRORS_SHEET, rows=max(len(rows), 10), cols=3)

    worksheet.update(values=rows, range_name="A1")


def write_warnings(spreadsheet: gspread.Spreadsheet, warnings: list[InputWarning]) -> None:
    """実行時に無視される入力値（設計書11章の「警告」相当）を出力_エラーシートへ追記する。

    実行を止めるエラーではないため、write_errorsとは別に呼び出す（write_errorsでシートを
    クリア・ヘッダーを書き込んだ後に呼び出すことを想定）。warningsが空なら何もしない。
    """

    if not warnings:
        return

    worksheet = spreadsheet.worksheet(OUTPUT_ERRORS_SHEET)
    existing_row_count = len(worksheet.get_all_values())
    rows = [[WARNING_KIND_LABEL, warning.field_path, warning.message] for warning in warnings]
    worksheet.update(values=rows, range_name=f"A{existing_row_count + 1}")
