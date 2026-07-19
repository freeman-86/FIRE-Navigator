from adapters.sheets.sample_data import (
    ACCOUNTS_ROWS,
    ALLOCATION_POLICY_ROWS,
    CHILDREN_ROWS,
    EDUCATION_EXPENSES_ROWS,
    EXPENSES_ROWS,
    INCOMES_ROWS,
    ONE_TIME_EXPENSES_ROWS,
    PLAN_ROWS,
    PROGRESS_ROWS,
    SCENARIOS_ROWS,
)
from adapters.sheets.sheet_mapping import (
    ACCOUNTS_SHEET,
    ALLOCATION_POLICY_SHEET,
    CHILDREN_SHEET,
    EDUCATION_EXPENSES_SHEET,
    EXPENSES_SHEET,
    INCOMES_SHEET,
    ONE_TIME_EXPENSES_SHEET,
    PLAN_SHEET,
    PROGRESS_SHEET,
    SCENARIOS_SHEET,
    SPREADSHEET_NAME,
)
from adapters.sheets.sheets_input_adapter import build_client, open_spreadsheet


def _seed_sheet(spreadsheet, sheet_name: str, rows: list[list[str]]) -> None:
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
    except Exception:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=max(len(rows), 10), cols=max(len(rows[0]), 5))
    worksheet.update(values=rows, range_name="A1")


def main() -> None:
    client = build_client()
    spreadsheet = open_spreadsheet(client, SPREADSHEET_NAME)

    _seed_sheet(spreadsheet, PLAN_SHEET, PLAN_ROWS)
    _seed_sheet(spreadsheet, ACCOUNTS_SHEET, ACCOUNTS_ROWS)
    _seed_sheet(spreadsheet, INCOMES_SHEET, INCOMES_ROWS)
    _seed_sheet(spreadsheet, EXPENSES_SHEET, EXPENSES_ROWS)
    _seed_sheet(spreadsheet, SCENARIOS_SHEET, SCENARIOS_ROWS)
    _seed_sheet(spreadsheet, PROGRESS_SHEET, PROGRESS_ROWS)
    _seed_sheet(spreadsheet, ALLOCATION_POLICY_SHEET, ALLOCATION_POLICY_ROWS)
    _seed_sheet(spreadsheet, CHILDREN_SHEET, CHILDREN_ROWS)
    _seed_sheet(spreadsheet, EDUCATION_EXPENSES_SHEET, EDUCATION_EXPENSES_ROWS)
    _seed_sheet(spreadsheet, ONE_TIME_EXPENSES_SHEET, ONE_TIME_EXPENSES_ROWS)

    print(f"サンプルデータを投入しました: {spreadsheet.url}")


if __name__ == "__main__":
    main()
