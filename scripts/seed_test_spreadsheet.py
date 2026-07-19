from adapters.sheets.sheet_mapping import (
    ACCOUNT_ID_HEADER,
    ACCOUNT_TYPE_HEADER,
    ACCOUNTS_SHEET,
    ACTUAL_NETWORTH_HEADER,
    AMOUNT_ANNUAL_HEADER,
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    BIRTH_DATE_HEADER,
    CATEGORY_HEADER,
    EMPLOYEE_PENSION_ESTIMATE_HEADER,
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
    MONTHLY_CONTRIBUTION_HEADER,
    NATIONAL_PENSION_ESTIMATE_HEADER,
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
    SPREADSHEET_NAME,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
    TARGET_ENDING_NETWORTH_HEADER,
    VOLATILITY_HEADER,
    YEAR_HEADER,
)
from adapters.sheets.sheets_input_adapter import build_client, open_spreadsheet

PLAN_ROWS = [
    [PLAN_ID_HEADER, "plan_001"],
    [PLAN_NAME_HEADER, "ベースプラン"],
    [BIRTH_DATE_HEADER, "1990-04-01"],
    [RESIDENCE_HEADER, "tokyo"],
    [INFLATION_RATE_HEADER, "0.02"],
    [INVESTMENT_GROWTH_RATE_HEADER, "0.05"],
    [RETIREMENT_AGE_HEADER, "60"],
    [NATIONAL_PENSION_ESTIMATE_HEADER, "780000"],
    [EMPLOYEE_PENSION_ESTIMATE_HEADER, "1200000"],
    [PENSION_CLAIM_TIMING_HEADER, "standard"],
    [PENSION_CLAIM_AGE_HEADER, "65"],
    [TARGET_ENDING_NETWORTH_HEADER, "20000000"],
]

ACCOUNTS_ROWS = [
    [
        ACCOUNT_ID_HEADER,
        ACCOUNT_TYPE_HEADER,
        OWNER_HEADER,
        BALANCE_HEADER,
        ASSET_CLASS_HEADER,
        EXPECTED_RETURN_HEADER,
        VOLATILITY_HEADER,
        MONTHLY_CONTRIBUTION_HEADER,
    ],
    ["acc_cash_001", "cash", "self", "1000000", "cash", "0.0", "0.0", ""],
    ["acc_nisa_growth_001", "nisa_growth", "self", "3000000", "equity_sp500", "0.05", "0.15", "50000"],
    ["acc_ideco_001", "ideco", "self", "1500000", "bond_us_treasury", "0.02", "0.05", "23000"],
]

INCOMES_ROWS = [
    [
        INCOME_ID_HEADER,
        SOURCE_HEADER,
        AMOUNT_ANNUAL_HEADER,
        GROWTH_RATE_HEADER,
        START_TYPE_HEADER,
        START_VALUE_HEADER,
        END_TYPE_HEADER,
        END_VALUE_HEADER,
    ],
    ["income_salary_001", "salary", "6000000", "0.01", "plan_start", "", "age", "60"],
]

EXPENSES_ROWS = [
    [EXPENSE_ID_HEADER, CATEGORY_HEADER, AMOUNT_ANNUAL_HEADER, GROWTH_RATE_HEADER, IS_FLEXIBLE_HEADER],
    ["expense_living_001", "living", "3600000", "0.02", "FALSE"],
]

SCENARIOS_ROWS = [
    [SCENARIO_ID_HEADER, SCENARIO_NAME_HEADER, RETIREMENT_AGE_HEADER],
    ["scenario_60", "60歳退職", "60"],
    ["scenario_65", "65歳退職", "65"],
]

PROGRESS_ROWS = [
    [YEAR_HEADER, ACTUAL_NETWORTH_HEADER],
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
