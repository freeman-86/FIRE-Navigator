from __future__ import annotations

SPREADSHEET_NAME = "FIRE-Navigator-test"

PLAN_SHEET = "Input_Plan"
ACCOUNTS_SHEET = "Input_Accounts"
INCOMES_SHEET = "Input_Incomes"
EXPENSES_SHEET = "Input_Expenses"
OUTPUT_NETWORTH_SHEET = "Output_NetWorth"

# Input_Plan: A列=キー / B列=値 の縦持ち設定シート。
# (シート上のキー, Planフィールドパス, 型変換ルール)
PLAN_FIELD_MAPPING: tuple[tuple[str, str, str], ...] = (
    ("plan_id", "plan.plan_id", "str"),
    ("name", "plan.name", "str"),
    ("birth_date", "plan.user.birth_date", "date"),
    ("residence", "plan.user.residence", "prefecture"),
    ("inflation_rate", "plan.assumptions.inflation_rate", "rate"),
    ("investment_growth_rate", "plan.assumptions.investment_growth_rate", "rate"),
)

# Input_Accounts: ヘッダー行付きテーブル。1行=1口座（保有資産は1件のみのシンプル構成）。
# (シート上の列名, Planフィールドパス, 型変換ルール)
ACCOUNTS_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    ("account_id", "plan.accounts[].account_id", "str"),
    ("account_type", "plan.accounts[].account_type", "account_type"),
    ("owner", "plan.accounts[].owner", "owner_type"),
    ("balance", "plan.accounts[].portfolio.holdings[].cost_basis", "money"),
    ("asset_class", "plan.accounts[].portfolio.holdings[].asset.asset_class", "asset_class"),
    ("expected_return", "plan.accounts[].portfolio.holdings[].asset.expected_return", "rate"),
    ("volatility", "plan.accounts[].portfolio.holdings[].asset.volatility", "rate"),
)

# Input_Incomes: ヘッダー行付きテーブル。
INCOMES_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    ("income_id", "plan.incomes[].income_id", "str"),
    ("source", "plan.incomes[].source", "str"),
    ("amount_annual", "plan.incomes[].amount", "money"),
    ("growth_rate", "plan.incomes[].growth_rate", "rate"),
    ("start_type", "plan.incomes[].start_condition.type", "condition_type"),
    ("start_value", "plan.incomes[].start_condition.value", "condition_value"),
    ("end_type", "plan.incomes[].end_condition.type", "condition_type"),
    ("end_value", "plan.incomes[].end_condition.value", "condition_value"),
)

# Input_Expenses: ヘッダー行付きテーブル。
EXPENSES_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    ("expense_id", "plan.expenses[].expense_id", "str"),
    ("category", "plan.expenses[].category", "str"),
    ("amount_annual", "plan.expenses[].amount", "money"),
    ("growth_rate", "plan.expenses[].growth_rate", "rate"),
    ("is_flexible", "plan.expenses[].is_flexible", "bool"),
)

# Output_NetWorth: ヘッダー行付きテーブル。西暦年別のネットワース数値のみを書き戻す最小版。
OUTPUT_NETWORTH_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    ("year", "simulation_result.yearly_projections[].year", "int"),
    ("networth", "simulation_result.yearly_projections[].networth", "money"),
)
