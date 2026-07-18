from __future__ import annotations

SPREADSHEET_NAME = "FIRE-Navigator-test"

PLAN_SHEET = "Input_Plan"
ACCOUNTS_SHEET = "Input_Accounts"
INCOMES_SHEET = "Input_Incomes"
EXPENSES_SHEET = "Input_Expenses"
SCENARIOS_SHEET = "Input_Scenarios"
OUTPUT_NETWORTH_SHEET = "Output_NetWorth"
OUTPUT_NETWORTH_BREAKDOWN_SHEET = "Output_NetWorth_Breakdown"
OUTPUT_SCENARIO_COMPARISON_SHEET = "Output_ScenarioComparison"
OUTPUT_SENSITIVITY_ANALYSIS_SHEET = "Output_SensitivityAnalysis"

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
# Account(Plan Aggregate)とPortfolio(独立したAggregate、account_idで参照)を同じシート行から組み立てる。
# (シート上の列名, フィールドパス, 型変換ルール)
ACCOUNTS_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    ("account_id", "plan.accounts[].account_id", "str"),
    ("account_type", "plan.accounts[].account_type", "account_type"),
    ("owner", "plan.accounts[].owner", "owner_type"),
    ("balance", "portfolios[account_id].holdings[].cost_basis", "money"),
    ("asset_class", "portfolios[account_id].holdings[].asset.asset_class", "asset_class"),
    ("expected_return", "portfolios[account_id].holdings[].asset.expected_return", "rate"),
    ("volatility", "portfolios[account_id].holdings[].asset.volatility", "rate"),
    ("monthly_contribution", "plan.accounts[].monthly_contribution", "money_optional"),
)

# Input_Scenarios: ヘッダー行付きテーブル。1行=1シナリオ（Scenario Aggregate）。
# 現時点でサポートするoverrideキーはretirement_ageのみ。
SCENARIOS_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    ("scenario_id", "scenario.scenario_id", "str"),
    ("name", "scenario.name", "str"),
    ("retirement_age", "scenario.overrides.retirement_age", "int"),
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

# Output_NetWorth_Breakdown: ヘッダー行付きテーブル。1列目=year、以降は口座種別（+unallocated_surplus）ごとの残高。
# 列数・列名はPlanのaccount構成によって可変なため固定のマッピング定義は持たず、
# reports/chart_builder.py の出力（charts.networth_chartのseries）からその都度組み立てる。
OUTPUT_NETWORTH_BREAKDOWN_FIELD_PATH = "output_json.charts.networth_chart"

# Output_ScenarioComparison: ヘッダー行付きテーブル。1列目=year、以降はシナリオ名ごとのネットワース推移。
# 列数・列名はInput_Scenariosの行数に応じて可変なため固定のマッピング定義は持たず、
# reports/scenario_comparison_builder.py の出力からその都度組み立てる。
OUTPUT_SCENARIO_COMPARISON_FIELD_PATH = "output_json.charts.scenario_comparison_chart"

# Output_SensitivityAnalysis: 成長率(行)×インフレ率(列)の最終年ネットワースをグリッド形式で書き出す。
# reports/sensitivity_analysis_builder.py の出力からその都度組み立てる。
OUTPUT_SENSITIVITY_ANALYSIS_FIELD_PATH = "output_json.tables.sensitivity_table"
