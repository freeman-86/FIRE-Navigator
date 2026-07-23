"""各入力シートのサンプル行データ。

scripts/seed_test_spreadsheet.py（テスト用スプレッドシートへの初期投入）と
adapters/sheets/sheets_formatting.py（「入力例」シートへの記入例の書き出し）の
両方から参照される、単一のサンプルデータ定義（値の食い違いを防ぐため一箇所に集約する）。
"""
from __future__ import annotations

from adapters.sheets.sheet_mapping import (
    ACCOUNT_ID_HEADER,
    ACCOUNT_TYPE_HEADER,
    ACTUAL_NETWORTH_HEADER,
    AGE_CONDITION_LABEL,
    AGE_HEADER,
    AMOUNT_ANNUAL_HEADER,
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    BIRTH_DATE_HEADER,
    CATEGORY_HEADER,
    CHILD_ID_HEADER,
    COST_BASIS_HEADER,
    EDUCATION_BAND_ID_HEADER,
    EMPLOYEE_PENSION_ESTIMATE_HEADER,
    END_AGE_HEADER,
    END_TYPE_HEADER,
    END_VALUE_HEADER,
    EXPECTED_RETURN_HEADER,
    EXPENSE_ID_HEADER,
    GROWTH_RATE_HEADER,
    INCOME_ID_HEADER,
    INFLATION_RATE_HEADER,
    INVESTMENT_GROWTH_RATE_HEADER,
    LIFE_EXPECTANCY_HEADER,
    MONTHLY_AMOUNT_HEADER,
    MONTHLY_CONTRIBUTION_HEADER,
    NATIONAL_PENSION_ESTIMATE_HEADER,
    ONE_TIME_AMOUNT_HEADER,
    ONE_TIME_FLAG_HEADER,
    PENSION_CLAIM_AGE_HEADER,
    PENSION_CLAIM_TIMING_HEADER,
    PLAN_ID_HEADER,
    PLAN_NAME_HEADER,
    PLAN_START_CONDITION_LABEL,
    RETIREMENT_AGE_HEADER,
    SCENARIO_ID_HEADER,
    SCENARIO_NAME_HEADER,
    SOURCE_HEADER,
    START_AGE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
    TARGET_ENDING_NETWORTH_HEADER,
    TARGET_WEIGHT_HEADER,
    YEAR_HEADER,
)

PLAN_ROWS = [
    [PLAN_ID_HEADER, "plan_001"],
    [PLAN_NAME_HEADER, "ベースプラン"],
    [BIRTH_DATE_HEADER, "1990-04-01"],
    [INFLATION_RATE_HEADER, "0.02"],
    [INVESTMENT_GROWTH_RATE_HEADER, "0.05"],
    [RETIREMENT_AGE_HEADER, "60"],
    [LIFE_EXPECTANCY_HEADER, "100"],
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
        BALANCE_HEADER,
        ASSET_CLASS_HEADER,
        EXPECTED_RETURN_HEADER,
        MONTHLY_CONTRIBUTION_HEADER,
        COST_BASIS_HEADER,
    ],
    ["acc_cash_001", "cash", "1000000", "cash", "0.0", "", ""],
    ["acc_nisa_growth_001", "nisa_growth", "3000000", "equity_sp500", "0.05", "50000", ""],
    ["acc_ideco_001", "ideco", "1500000", "bond_us_treasury", "0.02", "23000", ""],
    # 取得原価を残高より低く指定する例（含み益500,000円がある状態からシミュレーションを開始する）
    ["acc_taxable_001", "taxable", "2000000", "equity_sp500", "0.05", "30000", "1500000"],
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
    ["income_salary_001", "salary", "6000000", "0.01", PLAN_START_CONDITION_LABEL, "", AGE_CONDITION_LABEL, "60"],
]

EXPENSES_ROWS = [
    [
        EXPENSE_ID_HEADER,
        CATEGORY_HEADER,
        ONE_TIME_FLAG_HEADER,
        AMOUNT_ANNUAL_HEADER,
        ONE_TIME_AMOUNT_HEADER,
        GROWTH_RATE_HEADER,
        START_TYPE_HEADER,
        START_VALUE_HEADER,
        END_TYPE_HEADER,
        END_VALUE_HEADER,
    ],
    ["expense_living_001", "living", "FALSE", "3600000", "", "0.02", "", "", "", ""],
    # 経常支出も開始/終了条件を指定できる例（本人が50歳から60歳の間だけ発生する支出）。
    # 途中で金額が変わる支出は、開始/終了条件をずらした複数行に分けて表現する。
    [
        "expense_parent_care_001",
        "親の介護費用",
        "FALSE",
        "1200000",
        "",
        "0",
        AGE_CONDITION_LABEL,
        "50",
        AGE_CONDITION_LABEL,
        "60",
    ],
    ["expense_car_001", "車の買い替え", "TRUE", "", "3000000", "", AGE_CONDITION_LABEL, "45", "", ""],
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

ALLOCATION_POLICY_ROWS = [
    [AGE_HEADER, ASSET_CLASS_HEADER, TARGET_WEIGHT_HEADER],
    ["30", "equity_sp500", "0.8"],
    ["30", "bond_us_treasury", "0.2"],
    ["60", "equity_sp500", "0.4"],
    ["60", "bond_us_treasury", "0.6"],
]

EDUCATION_EXPENSES_ROWS = [
    [
        EDUCATION_BAND_ID_HEADER,
        CHILD_ID_HEADER,
        BIRTH_DATE_HEADER,
        CATEGORY_HEADER,
        START_AGE_HEADER,
        END_AGE_HEADER,
        MONTHLY_AMOUNT_HEADER,
    ],
    ["band_elementary", "child_001", "2022-04-01", "小学校", "6", "11", "20000"],
    ["band_juku", "child_001", "2022-04-01", "塾", "10", "11", "15000"],
    ["band_junior_high", "child_001", "2022-04-01", "中学校", "12", "14", "30000"],
    ["band_high_school", "child_001", "2022-04-01", "高校", "15", "17", "40000"],
    ["band_university", "child_001", "2022-04-01", "大学", "18", "21", "100000"],
]
