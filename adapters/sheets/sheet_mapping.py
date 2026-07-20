from __future__ import annotations

SPREADSHEET_NAME = "FIRE-Navigator-test"

# シートのタブ名。すべてこのファイルの定数を経由し、他ファイルに生文字列を持たせない
# （読み書きで表記が食い違うのを防ぐため）。
PLAN_SHEET = "入力_プラン設定"
ACCOUNTS_SHEET = "入力_口座"
INCOMES_SHEET = "入力_収入"
EXPENSES_SHEET = "入力_支出"
SCENARIOS_SHEET = "入力_シナリオ"
PROGRESS_SHEET = "入力_実績"
ALLOCATION_POLICY_SHEET = "入力_配分方針"
EDUCATION_EXPENSES_SHEET = "入力_教育費"
OUTPUT_NETWORTH_SHEET = "出力_純資産推移"
OUTPUT_NETWORTH_BREAKDOWN_SHEET = "出力_純資産内訳"
OUTPUT_SCENARIO_COMPARISON_SHEET = "出力_シナリオ比較"
OUTPUT_SENSITIVITY_ANALYSIS_SHEET = "出力_感応度分析"
OUTPUT_MONTECARLO_SHEET = "出力_モンテカルロ"
OUTPUT_HISTORICAL_BACKTEST_SHEET = "出力_ヒストリカルバックテスト"
OUTPUT_PROGRESS_COMPARISON_SHEET = "出力_計画実績比較"
OUTPUT_ERRORS_SHEET = "出力_エラー"
OUTPUT_DASHBOARD_SHEET = "出力_ダッシュボード"
OUTPUT_MONTHLY_DETAIL_SHEET = "出力_月次詳細"

# --- 列名（ヘッダー行）。account_type/asset_class等の「値」は内部識別子として英語のまま維持し、
# 列名（ヘッダーテキスト）のみ日本語化する。NISA/iDeCoは制度の正式名称のため英語表記を維持する。 ---

# Input_プラン設定: A列=キー / B列=値 の縦持ち設定シート。
# 旧ドラフトのMasterシート（主要条件をまとめて素早く変更できる単一シート）の方向性を踏襲し、
# 退職年齢・年金条件・目標資産もここに集約する（口座/収入/支出等の表形式シートとは別に
# 複製ビューを作らず、単一の置き場所に統一することで値の食い違いを防ぐ）。
PLAN_ID_HEADER = "プランID"
PLAN_NAME_HEADER = "プラン名"
BIRTH_DATE_HEADER = "生年月日"
RESIDENCE_HEADER = "居住都道府県"
INFLATION_RATE_HEADER = "インフレ率"
INVESTMENT_GROWTH_RATE_HEADER = "投資成長率"
NATIONAL_PENSION_ESTIMATE_HEADER = "国民年金見込額（年額）"
EMPLOYEE_PENSION_ESTIMATE_HEADER = "厚生年金見込額（年額）"
PENSION_CLAIM_TIMING_HEADER = "年金受給タイミング"
PENSION_CLAIM_AGE_HEADER = "年金受給開始年齢"
TARGET_ENDING_NETWORTH_HEADER = "目標資産（想定寿命時点）"

# Input_口座
ACCOUNT_ID_HEADER = "口座ID"
ACCOUNT_TYPE_HEADER = "口座タイプ"
OWNER_HEADER = "名義"
BALANCE_HEADER = "残高"
# 取得原価: 任意入力。未入力の場合は残高と同額（含み益ゼロ）とみなす。譲渡税計算（平均取得原価方式）で
# シミュレーション開始前からの含み益/含み損を反映するために使う（Holding.cost_basis）。
COST_BASIS_HEADER = "取得原価"
ASSET_CLASS_HEADER = "資産クラス"
EXPECTED_RETURN_HEADER = "期待リターン"
VOLATILITY_HEADER = "ボラティリティ"
MONTHLY_CONTRIBUTION_HEADER = "月次拠出額"

# Input_収入
AMOUNT_ANNUAL_HEADER = "年間金額"
GROWTH_RATE_HEADER = "成長率"
INCOME_ID_HEADER = "収入ID"
SOURCE_HEADER = "収入源"
START_TYPE_HEADER = "開始条件タイプ"
START_VALUE_HEADER = "開始条件値"
END_TYPE_HEADER = "終了条件タイプ"
END_VALUE_HEADER = "終了条件値"

# Input_支出: 経常支出（毎年発生・成長率あり）と単発支出（発生条件で1回のみ）を
# ONE_TIME_FLAG_HEADERで区別し、1シートにまとめる（旧Input_大型支出を統合）。
# 単発フラグ=TRUEの行はEXPENSE_AMOUNT_HEADER/START_TYPE_HEADER/START_VALUE_HEADERを使い、
# GROWTH_RATE_HEADER/IS_FLEXIBLE_HEADERは空欄でよい（経常支出専用）。
EXPENSE_ID_HEADER = "支出ID"
CATEGORY_HEADER = "カテゴリ"
IS_FLEXIBLE_HEADER = "柔軟支出フラグ"
ONE_TIME_FLAG_HEADER = "単発フラグ"
EXPENSE_AMOUNT_HEADER = "金額"

# Input_シナリオ
SCENARIO_ID_HEADER = "シナリオID"
SCENARIO_NAME_HEADER = "シナリオ名"
RETIREMENT_AGE_HEADER = "退職年齢"

# Input_配分方針: 年齢×資産クラスごとに1行。同じ年齢の行をまとめて1つのAllocationTargetとする
# （ギャップ分析3.7。プラン全体で1つ、口座横断の目標配分比率テーブル）。
AGE_HEADER = "年齢"
TARGET_WEIGHT_HEADER = "目標比率"

# Input_教育費: 子供ID×年齢帯×カテゴリごとに1行（ギャップ分析3.2）。旧Input_子供を統合しており、
# BIRTH_DATE_HEADERは同じ子供IDの行すべてに繰り返し記入する（行間で値が食い違うとエラーになる）。
CHILD_ID_HEADER = "子供ID"
EDUCATION_BAND_ID_HEADER = "教育費ID"
START_AGE_HEADER = "開始年齢"
END_AGE_HEADER = "終了年齢"
MONTHLY_AMOUNT_HEADER = "月額"

# Input_実績 / Output_純資産推移等で共通
YEAR_HEADER = "西暦年"
ACTUAL_NETWORTH_HEADER = "実績純資産"
NETWORTH_HEADER = "純資産"
CAPITAL_GAINS_TAX_HEADER = "譲渡税"

# Output_月次詳細: 月次の資金の動きをそのまま一覧表示する（Sprint12 月次化のmonthly_projections）。
MONTH_HEADER = "月"
NET_INCOME_HEADER = "手取り収入"
TOTAL_EXPENSE_HEADER = "支出"
NET_CASHFLOW_HEADER = "収支"

# Output_モンテカルロ / Output_ヒストリカルバックテスト
P10_HEADER = "下位10%値"
P50_HEADER = "中央値"
P90_HEADER = "上位10%値"

SENSITIVITY_TABLE_HEADER = "投資成長率＼インフレ率"

# Output_エラー: 種別列で「エラー」（実行を止める入力ミス）と「警告」（実行は続けるが
# 無視される入力値がある旨の注意喚起）を区別する。
KIND_HEADER = "種別"
FIELD_PATH_HEADER = "エラー箇所"
MESSAGE_HEADER = "エラー内容"
ERROR_KIND_LABEL = "エラー"
WARNING_KIND_LABEL = "警告"

# Output_ダッシュボード: A列=項目 / B列=値 の縦持ち集約ビュー（旧ドラフトのDashboardシートを踏襲）。
DASHBOARD_CURRENT_NETWORTH_LABEL = "現在の純資産"
DASHBOARD_EXTRA_ANNUAL_BUDGET_LABEL = "追加で使える金額（年額・暫定）"
DASHBOARD_EXTRA_MONTHLY_BUDGET_LABEL = "追加で使える金額（月額換算・暫定）"
DASHBOARD_DEPLETION_AGE_LABEL = "資産枯渇年齢"
DASHBOARD_TARGET_NETWORTH_LABEL = "目標資産（想定寿命時点）"
DASHBOARD_ENDING_NETWORTH_LABEL = "想定寿命時点の予測純資産"
DASHBOARD_SURPLUS_LABEL = "目標資産との余裕（想定寿命時点）"
DASHBOARD_NO_DEPLETION_TEXT = "枯渇なし"

# --- シート・セル・JSONフィールドパスの対応表（設計書7.3）。programmatic には未使用だが、
# レイアウト変更時の一元的な参照ドキュメントとして維持する。 ---

# (シート上のキー, Planフィールドパス, 型変換ルール)
PLAN_FIELD_MAPPING: tuple[tuple[str, str, str], ...] = (
    (PLAN_ID_HEADER, "plan.plan_id", "str"),
    (PLAN_NAME_HEADER, "plan.name", "str"),
    (BIRTH_DATE_HEADER, "plan.user.birth_date", "date"),
    (RESIDENCE_HEADER, "plan.user.residence", "prefecture"),
    (INFLATION_RATE_HEADER, "plan.assumptions.inflation_rate", "rate"),
    (INVESTMENT_GROWTH_RATE_HEADER, "plan.assumptions.investment_growth_rate", "rate"),
)

# Input_口座: ヘッダー行付きテーブル。1行=1口座（保有資産は1件のみのシンプル構成）。
# Account(Plan Aggregate)とPortfolio(独立したAggregate、account_idで参照)を同じシート行から組み立てる。
# (シート上の列名, フィールドパス, 型変換ルール)
ACCOUNTS_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    (ACCOUNT_ID_HEADER, "plan.accounts[].account_id", "str"),
    (ACCOUNT_TYPE_HEADER, "plan.accounts[].account_type", "account_type"),
    (OWNER_HEADER, "plan.accounts[].owner", "owner_type"),
    (BALANCE_HEADER, "portfolios[account_id].holdings[].current_value", "money"),
    (COST_BASIS_HEADER, "portfolios[account_id].holdings[].cost_basis", "money_optional"),
    (ASSET_CLASS_HEADER, "portfolios[account_id].holdings[].asset.asset_class", "asset_class"),
    (EXPECTED_RETURN_HEADER, "portfolios[account_id].holdings[].asset.expected_return", "rate"),
    (VOLATILITY_HEADER, "portfolios[account_id].holdings[].asset.volatility", "rate"),
    (MONTHLY_CONTRIBUTION_HEADER, "plan.accounts[].monthly_contribution", "money_optional"),
)

# Input_シナリオ: ヘッダー行付きテーブル。1行=1シナリオ（Scenario Aggregate）。
# 現時点でサポートするoverrideキーはretirement_ageのみ。
SCENARIOS_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    (SCENARIO_ID_HEADER, "scenario.scenario_id", "str"),
    (SCENARIO_NAME_HEADER, "scenario.name", "str"),
    (RETIREMENT_AGE_HEADER, "scenario.overrides.retirement_age", "int"),
)

# Input_実績: ヘッダー行付きテーブル。1行=1年分の実績ネットワース。
PROGRESS_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    (YEAR_HEADER, "progress_record.year", "int"),
    (ACTUAL_NETWORTH_HEADER, "progress_record.actual_networth", "money"),
)

# Input_配分方針: ヘッダー行付きテーブル。1行=(年齢, 資産クラス, 目標比率)。任意入力。
ALLOCATION_POLICY_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    (AGE_HEADER, "plan.allocation_policy.targets[].age", "int"),
    (ASSET_CLASS_HEADER, "plan.allocation_policy.targets[].weights{}", "asset_class"),
    (TARGET_WEIGHT_HEADER, "plan.allocation_policy.targets[].weights{}", "rate"),
)

# Input_教育費: ヘッダー行付きテーブル。1行=1教育費バンド。任意入力。BIRTH_DATE_HEADERから
# plan.children（同じchild_idの行で重複排除）も組み立てる（旧Input_子供を統合）。
EDUCATION_EXPENSES_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    (EDUCATION_BAND_ID_HEADER, "plan.education_expenses[].band_id", "str"),
    (CHILD_ID_HEADER, "plan.education_expenses[].child_id", "str"),
    (BIRTH_DATE_HEADER, "plan.children[].birth_date", "date"),
    (CATEGORY_HEADER, "plan.education_expenses[].category", "str"),
    (START_AGE_HEADER, "plan.education_expenses[].start_age", "int"),
    (END_AGE_HEADER, "plan.education_expenses[].end_age", "int"),
    (MONTHLY_AMOUNT_HEADER, "plan.education_expenses[].monthly_amount", "money"),
)

# Input_収入: ヘッダー行付きテーブル。
INCOMES_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    (INCOME_ID_HEADER, "plan.incomes[].income_id", "str"),
    (SOURCE_HEADER, "plan.incomes[].source", "str"),
    (AMOUNT_ANNUAL_HEADER, "plan.incomes[].amount", "money"),
    (GROWTH_RATE_HEADER, "plan.incomes[].growth_rate", "rate"),
    (START_TYPE_HEADER, "plan.incomes[].start_condition.type", "condition_type"),
    (START_VALUE_HEADER, "plan.incomes[].start_condition.value", "condition_value"),
    (END_TYPE_HEADER, "plan.incomes[].end_condition.type", "condition_type"),
    (END_VALUE_HEADER, "plan.incomes[].end_condition.value", "condition_value"),
)

# Input_支出: ヘッダー行付きテーブル。ONE_TIME_FLAG_HEADER=TRUEの行はplan.one_time_expenses[]へ、
# FALSE(既定)の行はplan.expenses[]へ振り分ける（旧Input_大型支出を統合）。
EXPENSES_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    (EXPENSE_ID_HEADER, "plan.expenses[].expense_id / plan.one_time_expenses[].expense_id", "str"),
    (CATEGORY_HEADER, "plan.expenses[].category / plan.one_time_expenses[].category", "str"),
    (ONE_TIME_FLAG_HEADER, "(振り分け用のみ、Plan本体には保持しない)", "bool"),
    (EXPENSE_AMOUNT_HEADER, "plan.expenses[].amount / plan.one_time_expenses[].amount", "money"),
    (GROWTH_RATE_HEADER, "plan.expenses[].growth_rate（経常支出のみ）", "rate"),
    (IS_FLEXIBLE_HEADER, "plan.expenses[].is_flexible（経常支出のみ）", "bool"),
    (START_TYPE_HEADER, "plan.one_time_expenses[].trigger.type（単発支出のみ）", "condition_type"),
    (START_VALUE_HEADER, "plan.one_time_expenses[].trigger.value（単発支出のみ）", "condition_value"),
)

# Output_純資産推移: ヘッダー行付きテーブル。西暦年別のネットワース・譲渡税を書き戻す。
OUTPUT_NETWORTH_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    (YEAR_HEADER, "simulation_result.yearly_projections[].year", "int"),
    (NETWORTH_HEADER, "simulation_result.yearly_projections[].networth", "money"),
    (CAPITAL_GAINS_TAX_HEADER, "simulation_result.yearly_projections[].capital_gains_tax", "money"),
)

# Output_月次詳細: ヘッダー行付きテーブル。西暦年・月別の月次明細を書き戻す。
OUTPUT_MONTHLY_DETAIL_COLUMN_MAPPING: tuple[tuple[str, str, str], ...] = (
    (YEAR_HEADER, "simulation_result.monthly_projections[].year", "int"),
    (MONTH_HEADER, "simulation_result.monthly_projections[].month", "int"),
    (AGE_HEADER, "simulation_result.monthly_projections[].age_self", "int"),
    (NET_INCOME_HEADER, "simulation_result.monthly_projections[].net_income", "money"),
    (TOTAL_EXPENSE_HEADER, "simulation_result.monthly_projections[].total_expense", "money"),
    (NET_CASHFLOW_HEADER, "simulation_result.monthly_projections[].net_cashflow", "money"),
    (CAPITAL_GAINS_TAX_HEADER, "simulation_result.monthly_projections[].capital_gains_tax", "money"),
    (NETWORTH_HEADER, "simulation_result.monthly_projections[].networth", "money"),
)

# Output_純資産内訳: ヘッダー行付きテーブル。1列目=year、以降は口座種別（+unallocated_surplus）ごとの残高。
# 列数・列名はPlanのaccount構成によって可変なため固定のマッピング定義は持たず、
# reports/chart_builder.py の出力（charts.networth_chartのseries）からその都度組み立てる。
OUTPUT_NETWORTH_BREAKDOWN_FIELD_PATH = "output_json.charts.networth_chart"

# Output_シナリオ比較: ヘッダー行付きテーブル。1列目=year、以降はシナリオ名ごとのネットワース推移。
# 列数・列名はInput_シナリオの行数に応じて可変なため固定のマッピング定義は持たず、
# reports/scenario_comparison_builder.py の出力からその都度組み立てる。
OUTPUT_SCENARIO_COMPARISON_FIELD_PATH = "output_json.charts.scenario_comparison_chart"

# Output_感応度分析: 成長率(行)×インフレ率(列)の最終年ネットワースをグリッド形式で書き出す。
# reports/sensitivity_analysis_builder.py の出力からその都度組み立てる。
OUTPUT_SENSITIVITY_ANALYSIS_FIELD_PATH = "output_json.tables.sensitivity_table"
