from __future__ import annotations

import gspread

from adapters.sheets.sheet_mapping import OUTPUT_ERRORS_SHEET
from core.domain.errors import FireNavigatorError


def write_errors(spreadsheet: gspread.Spreadsheet, errors: list[FireNavigatorError]) -> None:
    """検出されたエラーをOutput_Errorsシートへ「どのフィールドで・何が」の形で一覧表示する
    （設計書11.2〜11.3。例外を握りつぶさず、直すべき場所まで含めて返す）。
    """

    rows: list[list[object]] = [["field_path", "message"]]
    rows += [[error.field_path, error.message] for error in errors]

    try:
        worksheet = spreadsheet.worksheet(OUTPUT_ERRORS_SHEET)
        worksheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=OUTPUT_ERRORS_SHEET, rows=max(len(rows), 10), cols=2)

    worksheet.update(values=rows, range_name="A1")
