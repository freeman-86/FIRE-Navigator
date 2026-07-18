from adapters.sheets.sheet_mapping import (
    ACCOUNTS_SHEET,
    EXPENSES_SHEET,
    INCOMES_SHEET,
    PLAN_SHEET,
    PROGRESS_SHEET,
    SCENARIOS_SHEET,
    SPREADSHEET_NAME,
)
from adapters.sheets.sheets_input_adapter import build_client, open_spreadsheet

PLAN_ROWS = [
    ["plan_id", "plan_001"],
    ["name", "ベースプラン"],
    ["birth_date", "1990-04-01"],
    ["residence", "tokyo"],
    ["inflation_rate", "0.02"],
    ["investment_growth_rate", "0.05"],
]

ACCOUNTS_ROWS = [
    [
        "account_id",
        "account_type",
        "owner",
        "balance",
        "asset_class",
        "expected_return",
        "volatility",
        "monthly_contribution",
    ],
    ["acc_cash_001", "cash", "self", "1000000", "cash", "0.0", "0.0", ""],
    ["acc_nisa_growth_001", "nisa_growth", "self", "3000000", "global_equity", "0.05", "0.15", "50000"],
    ["acc_ideco_001", "ideco", "self", "1500000", "domestic_bond", "0.02", "0.05", "23000"],
]

INCOMES_ROWS = [
    ["income_id", "source", "amount_annual", "growth_rate", "start_type", "start_value", "end_type", "end_value"],
    ["income_salary_001", "salary", "6000000", "0.01", "plan_start", "", "age", "60"],
]

EXPENSES_ROWS = [
    ["expense_id", "category", "amount_annual", "growth_rate", "is_flexible"],
    ["expense_living_001", "living", "3600000", "0.02", "FALSE"],
]

SCENARIOS_ROWS = [
    ["scenario_id", "name", "retirement_age"],
    ["scenario_60", "60歳退職", "60"],
    ["scenario_65", "65歳退職", "65"],
]

PROGRESS_ROWS = [
    ["year", "actual_networth"],
    ["2026", "6800000"],
    ["2027", "7900000"],
]


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

    print(f"サンプルデータを投入しました: {spreadsheet.url}")


if __name__ == "__main__":
    main()
