from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from adapters.sheets.sheet_mapping import (
    ACCOUNT_ID_HEADER,
    ACCOUNT_TYPE_HEADER,
    ACCOUNTS_SHEET,
    ACTUAL_NETWORTH_HEADER,
    AGE_HEADER,
    ALLOCATION_POLICY_SHEET,
    AMOUNT_ANNUAL_HEADER,
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    BIRTH_DATE_HEADER,
    CATEGORY_HEADER,
    CHILD_ID_HEADER,
    COST_BASIS_HEADER,
    EDUCATION_BAND_ID_HEADER,
    EDUCATION_EXPENSES_SHEET,
    EMPLOYEE_PENSION_ESTIMATE_HEADER,
    END_AGE_HEADER,
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
    PLAN_SHEET,
    PROGRESS_SHEET,
    RETIREMENT_AGE_HEADER,
    SCENARIO_ID_HEADER,
    SCENARIO_NAME_HEADER,
    SCENARIOS_SHEET,
    SOURCE_HEADER,
    SPREADSHEET_NAME,
    START_AGE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
    TARGET_ENDING_NETWORTH_HEADER,
    TARGET_WEIGHT_HEADER,
    YEAR_HEADER,
)
from core.domain.account import Account, AccountType
from core.domain.allocation import AllocationPolicy, AllocationTarget
from core.domain.asset import Asset, AssetClass
from core.domain.child import Child
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.education_expense import EducationExpenseBand
from core.domain.errors import StructuralInputError
from core.domain.expense import Expense
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.milestone import Milestone, MilestoneType
from core.domain.one_time_expense import OneTimeExpense
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import DEFAULT_LIFE_EXPECTANCY_AGE, Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.progress_record import ProgressRecord
from core.domain.scenario import Scenario
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from repositories.asset_class_repository import load_asset_class_registry

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

DEFAULT_CREDENTIALS_PATH = "secrets/gsheets_credentials.json"


def build_client(credentials_path: str = DEFAULT_CREDENTIALS_PATH) -> gspread.Client:
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)


def open_spreadsheet(client: gspread.Client, spreadsheet_name: str = SPREADSHEET_NAME) -> gspread.Spreadsheet:
    return client.open(spreadsheet_name)


# --- 入力ミス検出用の共通ヘルパー（設計書11章 StructuralInputError） -----------------------------


def _require(record: dict, key: str, field_path: str) -> object:
    value = record.get(key)
    if value is None or str(value).strip() == "":
        raise StructuralInputError(f"必須項目が未入力です（列: {key}）", field_path)
    return value


def _parse_money(value: object, field_path: str) -> Money:
    try:
        return Money.of(_strip_thousands_separators(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise StructuralInputError(f"金額として解釈できない値です: {value!r}", field_path) from e


def _parse_money_or_zero(value: object, field_path: str) -> Money:
    """空欄なら0円として扱う金額列用。0円でも意味が成立する項目（残高・年間金額・単発金額・
    教育費の月額等）に使う。値が入っている場合は通常通り_parse_moneyで検証する
    （数値として解釈できない文字列はこれまで通りエラーにする）。
    """

    raw = str(value).strip() if value is not None else ""
    return _parse_money(raw, field_path) if raw else Money.zero()


def _strip_thousands_separators(value: object) -> object:
    """金額列にはカンマ区切り表示(#,##0)を設定しているため、get_all_values()経由（入力_プラン設定等の
    縦持ちシート）で読み込むとFORMATTED_VALUE（表示形式適用後の文字列）としてカンマ付きで返ってくる。
    get_all_records()経由の表形式シートはgspreadが自動でカンマを除去して数値化するため影響しないが、
    どちらの経路でも安全に扱えるよう、文字列の場合のみここでカンマを取り除く。
    """

    return value.replace(",", "") if isinstance(value, str) else value


def _parse_rate(value: object, field_path: str) -> Rate:
    try:
        return Rate.of(_normalize_percent_display(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise StructuralInputError(f"割合として解釈できない値です: {value!r}", field_path) from e


def _normalize_percent_display(value: object) -> object:
    """比率列にはパーセント表示形式(0.00%)を設定しているため、get_all_values()（入力_プラン設定等の
    縦持ちシート）・get_all_records()（表形式シート、gspreadのnumericise()は%記号を扱えず素通しする）の
    どちらの経路でも、FORMATTED_VALUE（表示形式適用後の文字列。例: "7.00%"）として返ってくることが
    ある。末尾が%の場合はパーセント表記とみなし、100で割った小数に変換する
    （Rate.ofが期待する生の小数表現に揃える）。
    """

    if isinstance(value, str) and value.strip().endswith("%"):
        return Decimal(value.strip().rstrip("%").replace(",", "")) / Decimal(100)
    return value


def _parse_growth_rate(record: dict, field_path: str, default_growth_rate: Rate) -> Rate:
    """成長率列。未入力の行はプラン設定のインフレ率を既定値として使う（入力済みの行はそちらを優先）。"""

    raw = str(record.get(GROWTH_RATE_HEADER, "")).strip()
    return _parse_rate(raw, field_path) if raw else default_growth_rate


def _parse_int(value: object, field_path: str) -> int:
    try:
        return int(str(value).strip())
    except ValueError as e:
        raise StructuralInputError(f"整数として解釈できない値です: {value!r}", field_path) from e


def _parse_date_field(value: object, field_path: str) -> date:
    try:
        return _parse_date(value)
    except ValueError as e:
        raise StructuralInputError(f"日付(YYYY-MM-DD形式)として解釈できない値です: {value!r}", field_path) from e


def _parse_enum(enum_cls, value: object, field_path: str):
    try:
        return enum_cls(value)
    except ValueError as e:
        allowed = ", ".join(member.value for member in enum_cls)
        raise StructuralInputError(
            f"未知の値です: {value!r}（有効な値: {allowed}）", field_path
        ) from e


def _parse_asset_class(value: object, field_path: str, asset_class_registry: dict[AssetClass, str]) -> AssetClass:
    code = str(value).strip()
    if code not in asset_class_registry:
        allowed = ", ".join(asset_class_registry.keys())
        raise StructuralInputError(
            f"未知の資産クラスです: {code!r}（有効な値: {allowed}）", field_path
        )
    return code


def _parse_bool(value: object) -> bool:
    return str(value).strip().upper() in ("TRUE", "1", "YES")


def _parse_date(value: object) -> date:
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def _build_event_condition(condition_type: object, value: object, field_path: str) -> Optional[EventCondition]:
    normalized_type = str(condition_type or "").strip().lower()
    normalized_value = str(value or "").strip()
    if normalized_type in ("", "none"):
        return None
    if normalized_type == "today":
        return EventCondition.today()
    if normalized_type == "plan_start":
        return EventCondition.plan_start()
    if normalized_type == "age":
        return EventCondition.at_age(_parse_int(normalized_value, field_path))
    if normalized_type == "date":
        return EventCondition.at_date(_parse_date_field(normalized_value, field_path))
    raise StructuralInputError(
        f"未知のcondition_typeです: {normalized_type!r}（有効な値: today, plan_start, age, date）", field_path
    )


def _read_plan_settings(spreadsheet: gspread.Spreadsheet) -> dict[str, str]:
    worksheet = spreadsheet.worksheet(PLAN_SHEET)
    rows = worksheet.get_all_values()
    return {row[0]: row[1] for row in rows if row and row[0]}


def _require_setting(settings: dict[str, str], key: str) -> str:
    value = settings.get(key, "").strip()
    if not value:
        raise StructuralInputError(
            f"必須項目が未入力です（{PLAN_SHEET}のA列に'{key}'の行がないか、B列が空です）", f"{PLAN_SHEET}!{key}"
        )
    return value


def _build_user(settings: dict[str, str]) -> User:
    return User(
        birth_date=_parse_date_field(_require_setting(settings, BIRTH_DATE_HEADER), f"{PLAN_SHEET}!{BIRTH_DATE_HEADER}"),
    )


def _build_assumptions(settings: dict[str, str]) -> Assumptions:
    return Assumptions(
        inflation_rate=_parse_rate(
            _require_setting(settings, INFLATION_RATE_HEADER), f"{PLAN_SHEET}!{INFLATION_RATE_HEADER}"
        ),
        investment_growth_rate=_parse_rate(
            _require_setting(settings, INVESTMENT_GROWTH_RATE_HEADER),
            f"{PLAN_SHEET}!{INVESTMENT_GROWTH_RATE_HEADER}",
        ),
    )


def _build_accounts(spreadsheet: gspread.Spreadsheet) -> list[Account]:
    worksheet = spreadsheet.worksheet(ACCOUNTS_SHEET)
    accounts = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{ACCOUNTS_SHEET}!row{row_number}"
        account_id = str(_require(record, ACCOUNT_ID_HEADER, f"{row_prefix}.{ACCOUNT_ID_HEADER}"))
        monthly_contribution_raw = str(record.get(MONTHLY_CONTRIBUTION_HEADER, "")).strip()
        accounts.append(
            Account(
                account_id=account_id,
                account_type=_parse_enum(
                    AccountType,
                    _require(record, ACCOUNT_TYPE_HEADER, f"{row_prefix}.{ACCOUNT_TYPE_HEADER}"),
                    f"{row_prefix}.{ACCOUNT_TYPE_HEADER}",
                ),
                monthly_contribution=(
                    _parse_money(monthly_contribution_raw, f"{row_prefix}.{MONTHLY_CONTRIBUTION_HEADER}")
                    if monthly_contribution_raw
                    else None
                ),
            )
        )
    return accounts


def build_portfolios_from_spreadsheet(
    spreadsheet: gspread.Spreadsheet, asset_class_registry: Optional[dict[AssetClass, str]] = None
) -> dict[str, Portfolio]:
    """Portfolio Aggregate（account_idで参照される独立集約）を入力_口座シートから組み立てる。

    asset_class_registryは資産クラス識別子の妥当性検証に使う（省略時はconfig/asset_classes.yamlを
    読み込む）。新しい資産クラスを追加してもこの関数のロジックは変更不要（設計書3.2）。
    """

    if asset_class_registry is None:
        asset_class_registry = load_asset_class_registry()

    worksheet = spreadsheet.worksheet(ACCOUNTS_SHEET)
    portfolios: dict[str, Portfolio] = {}
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{ACCOUNTS_SHEET}!row{row_number}"
        account_id = str(_require(record, ACCOUNT_ID_HEADER, f"{row_prefix}.{ACCOUNT_ID_HEADER}"))
        asset = Asset(
            asset_class=_parse_asset_class(
                _require(record, ASSET_CLASS_HEADER, f"{row_prefix}.{ASSET_CLASS_HEADER}"),
                f"{row_prefix}.{ASSET_CLASS_HEADER}",
                asset_class_registry,
            ),
            expected_return=_parse_rate(
                _require(record, EXPECTED_RETURN_HEADER, f"{row_prefix}.{EXPECTED_RETURN_HEADER}"),
                f"{row_prefix}.{EXPECTED_RETURN_HEADER}",
            ),
        )
        current_value = _parse_money_or_zero(record.get(BALANCE_HEADER, ""), f"{row_prefix}.{BALANCE_HEADER}")
        cost_basis_raw = str(record.get(COST_BASIS_HEADER, "")).strip()
        # 取得原価が未入力の場合は残高と同額とみなす（開始時点の含み益ゼロという後方互換のデフォルト）
        cost_basis = (
            _parse_money(cost_basis_raw, f"{row_prefix}.{COST_BASIS_HEADER}") if cost_basis_raw else current_value
        )
        holding = Holding(asset=asset, quantity=1, current_value=current_value, cost_basis=cost_basis)
        portfolios[account_id] = Portfolio(holdings=[holding])
    return portfolios


def build_scenarios_from_spreadsheet(spreadsheet: gspread.Spreadsheet, plan_id: str) -> list[Scenario]:
    """Scenario Aggregate（plan_idで参照される独立集約）を入力_シナリオシートから組み立てる。

    入力_シナリオシートが存在しない場合は空リストを返す（シナリオ比較はオプション機能）。
    """

    try:
        worksheet = spreadsheet.worksheet(SCENARIOS_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        return []

    scenarios = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{SCENARIOS_SHEET}!row{row_number}"
        overrides = {}
        retirement_age_raw = str(record.get(RETIREMENT_AGE_HEADER, "")).strip()
        if retirement_age_raw:
            overrides["retirement_age"] = _parse_int(retirement_age_raw, f"{row_prefix}.{RETIREMENT_AGE_HEADER}")
        scenarios.append(
            Scenario(
                scenario_id=str(_require(record, SCENARIO_ID_HEADER, f"{row_prefix}.{SCENARIO_ID_HEADER}")),
                plan_id=plan_id,
                name=str(_require(record, SCENARIO_NAME_HEADER, f"{row_prefix}.{SCENARIO_NAME_HEADER}")),
                overrides=overrides,
            )
        )
    return scenarios


def build_progress_records_from_spreadsheet(spreadsheet: gspread.Spreadsheet) -> list[ProgressRecord]:
    """実績ネットワースを入力_実績シートから読み込む。

    入力_実績シートが存在しない場合は空リストを返す（Progress比較はオプション機能）。
    """

    try:
        worksheet = spreadsheet.worksheet(PROGRESS_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        return []

    records = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{PROGRESS_SHEET}!row{row_number}"
        records.append(
            ProgressRecord(
                year=_parse_int(_require(record, YEAR_HEADER, f"{row_prefix}.{YEAR_HEADER}"), f"{row_prefix}.{YEAR_HEADER}"),
                actual_networth=_parse_money(
                    _require(record, ACTUAL_NETWORTH_HEADER, f"{row_prefix}.{ACTUAL_NETWORTH_HEADER}"),
                    f"{row_prefix}.{ACTUAL_NETWORTH_HEADER}",
                ),
            )
        )
    return records


def _build_allocation_policy(
    spreadsheet: gspread.Spreadsheet, asset_class_registry: Optional[dict[AssetClass, str]] = None
) -> Optional[AllocationPolicy]:
    """年齢別の目標配分比率（プラン全体で1つ、口座横断）を入力_配分方針シートから組み立てる。

    入力_配分方針シートが存在しない場合はNoneを返す（資産配分比率の可変対応・月次リバランスは
    オプション機能。ギャップ分析3.7）。1行=(年齢, 資産クラス, 目標比率)で、同じ年齢の行をまとめて
    1つのAllocationTargetにする。
    """

    try:
        worksheet = spreadsheet.worksheet(ALLOCATION_POLICY_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        return None

    if asset_class_registry is None:
        asset_class_registry = load_asset_class_registry()

    weights_by_age: dict[int, dict[AssetClass, Rate]] = {}
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{ALLOCATION_POLICY_SHEET}!row{row_number}"
        age = _parse_int(_require(record, AGE_HEADER, f"{row_prefix}.{AGE_HEADER}"), f"{row_prefix}.{AGE_HEADER}")
        asset_class = _parse_asset_class(
            _require(record, ASSET_CLASS_HEADER, f"{row_prefix}.{ASSET_CLASS_HEADER}"),
            f"{row_prefix}.{ASSET_CLASS_HEADER}",
            asset_class_registry,
        )
        weight = _parse_rate(
            _require(record, TARGET_WEIGHT_HEADER, f"{row_prefix}.{TARGET_WEIGHT_HEADER}"),
            f"{row_prefix}.{TARGET_WEIGHT_HEADER}",
        )
        weights_by_age.setdefault(age, {})[asset_class] = weight

    targets = [
        AllocationTarget(age=age, weights=weights) for age, weights in sorted(weights_by_age.items())
    ]
    return AllocationPolicy(targets=targets)


def _build_children_and_education_expenses(
    spreadsheet: gspread.Spreadsheet,
) -> tuple[list[Child], list[EducationExpenseBand]]:
    """子供の一覧と年齢帯別の教育費を入力_教育費シートから組み立てる（ギャップ分析3.2）。

    旧Input_子供シートを統合しており、BIRTH_DATE_HEADERは同じ子供IDの行すべてに繰り返し記入する
    想定（行間で値が食い違う場合はStructuralInputErrorを送出し、入力ミスを早期に検出する）。
    入力_教育費シートが存在しない場合は空リストを返す（教育費機能はオプション機能）。
    """

    try:
        worksheet = spreadsheet.worksheet(EDUCATION_EXPENSES_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        return [], []

    children_by_id: dict[str, Child] = {}
    bands = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{EDUCATION_EXPENSES_SHEET}!row{row_number}"
        child_id = str(_require(record, CHILD_ID_HEADER, f"{row_prefix}.{CHILD_ID_HEADER}"))
        birth_date = _parse_date_field(
            _require(record, BIRTH_DATE_HEADER, f"{row_prefix}.{BIRTH_DATE_HEADER}"),
            f"{row_prefix}.{BIRTH_DATE_HEADER}",
        )
        existing_child = children_by_id.get(child_id)
        if existing_child is not None and existing_child.birth_date != birth_date:
            raise StructuralInputError(
                f"同じ{CHILD_ID_HEADER}で{BIRTH_DATE_HEADER}が行ごとに一致しません"
                f"（{existing_child.birth_date} と {birth_date}）",
                f"{row_prefix}.{BIRTH_DATE_HEADER}",
            )
        children_by_id.setdefault(child_id, Child(child_id=child_id, birth_date=birth_date))

        bands.append(
            EducationExpenseBand(
                band_id=str(_require(record, EDUCATION_BAND_ID_HEADER, f"{row_prefix}.{EDUCATION_BAND_ID_HEADER}")),
                child_id=child_id,
                category=str(_require(record, CATEGORY_HEADER, f"{row_prefix}.{CATEGORY_HEADER}")),
                start_age=_parse_int(
                    _require(record, START_AGE_HEADER, f"{row_prefix}.{START_AGE_HEADER}"),
                    f"{row_prefix}.{START_AGE_HEADER}",
                ),
                end_age=_parse_int(
                    _require(record, END_AGE_HEADER, f"{row_prefix}.{END_AGE_HEADER}"),
                    f"{row_prefix}.{END_AGE_HEADER}",
                ),
                monthly_amount=_parse_money_or_zero(
                    record.get(MONTHLY_AMOUNT_HEADER, ""), f"{row_prefix}.{MONTHLY_AMOUNT_HEADER}"
                ),
            )
        )
    return list(children_by_id.values()), bands


def _build_incomes(spreadsheet: gspread.Spreadsheet, default_growth_rate: Rate) -> list[Income]:
    """収入一覧を入力_収入シートから組み立てる。

    成長率(GROWTH_RATE_HEADER)が未入力の行は、プラン設定のインフレ率(default_growth_rate)を
    既定値として使う（入力済みの行はそちらを優先する）。
    """

    worksheet = spreadsheet.worksheet(INCOMES_SHEET)
    incomes = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{INCOMES_SHEET}!row{row_number}"
        start_condition = _build_event_condition(
            record.get(START_TYPE_HEADER), record.get(START_VALUE_HEADER), f"{row_prefix}.{START_TYPE_HEADER}"
        )
        if start_condition is None:
            raise StructuralInputError(f"{START_TYPE_HEADER}が必須です", f"{row_prefix}.{START_TYPE_HEADER}")
        end_condition = _build_event_condition(
            record.get(END_TYPE_HEADER), record.get(END_VALUE_HEADER), f"{row_prefix}.{END_TYPE_HEADER}"
        )
        incomes.append(
            Income(
                income_id=str(_require(record, INCOME_ID_HEADER, f"{row_prefix}.{INCOME_ID_HEADER}")),
                source=str(_require(record, SOURCE_HEADER, f"{row_prefix}.{SOURCE_HEADER}")),
                amount=_parse_money_or_zero(record.get(AMOUNT_ANNUAL_HEADER, ""), f"{row_prefix}.{AMOUNT_ANNUAL_HEADER}"),
                growth_rate=_parse_growth_rate(record, f"{row_prefix}.{GROWTH_RATE_HEADER}", default_growth_rate),
                start_condition=start_condition,
                end_condition=end_condition,
            )
        )
    return incomes


def _build_expenses(
    spreadsheet: gspread.Spreadsheet, default_growth_rate: Rate
) -> tuple[list[Expense], list[OneTimeExpense]]:
    """経常支出と単発支出（旧Input_大型支出）を入力_支出シートから組み立てる。

    ONE_TIME_FLAG_HEADER=TRUEの行は単発支出（発生条件で1回のみ、金額はONE_TIME_AMOUNT_HEADER）、
    それ以外(既定FALSE)は経常支出（毎年発生・成長率あり、金額はAMOUNT_ANNUAL_HEADER）として
    振り分ける。経常支出の成長率が未入力の行は、プラン設定のインフレ率(default_growth_rate)を
    既定値として使う（入力済みの行はそちらを優先）。
    """

    worksheet = spreadsheet.worksheet(EXPENSES_SHEET)
    expenses = []
    one_time_expenses = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{EXPENSES_SHEET}!row{row_number}"
        expense_id = str(_require(record, EXPENSE_ID_HEADER, f"{row_prefix}.{EXPENSE_ID_HEADER}"))
        category = str(_require(record, CATEGORY_HEADER, f"{row_prefix}.{CATEGORY_HEADER}"))

        if _parse_bool(record.get(ONE_TIME_FLAG_HEADER, "FALSE")):
            amount = _parse_money_or_zero(record.get(ONE_TIME_AMOUNT_HEADER, ""), f"{row_prefix}.{ONE_TIME_AMOUNT_HEADER}")
            trigger = _build_event_condition(
                record.get(START_TYPE_HEADER), record.get(START_VALUE_HEADER), f"{row_prefix}.{START_TYPE_HEADER}"
            )
            if trigger is None:
                raise StructuralInputError(
                    f"{START_TYPE_HEADER}が必須です（{ONE_TIME_FLAG_HEADER}=TRUEの行）", f"{row_prefix}.{START_TYPE_HEADER}"
                )
            one_time_expenses.append(
                OneTimeExpense(expense_id=expense_id, category=category, amount=amount, trigger=trigger)
            )
        else:
            amount = _parse_money_or_zero(record.get(AMOUNT_ANNUAL_HEADER, ""), f"{row_prefix}.{AMOUNT_ANNUAL_HEADER}")
            growth_rate = _parse_growth_rate(record, f"{row_prefix}.{GROWTH_RATE_HEADER}", default_growth_rate)
            expenses.append(
                Expense(
                    expense_id=expense_id,
                    category=category,
                    amount=amount,
                    growth_rate=growth_rate,
                )
            )
    return expenses, one_time_expenses


def _default_tax_config() -> TaxConfig:
    return TaxConfig()


def _build_pension(settings: dict[str, str]) -> Pension:
    """入力_プラン設定（Master的な要約入力ビュー）の年金4項目からPensionを組み立てる。

    すべて任意入力。未入力の項目は年金見込額ゼロ・標準65歳受給という後方互換のデフォルトを使う
    （このMaster項目が追加される以前は、年金条件はSheetsから一切編集できなかった）。
    """

    national_raw = settings.get(NATIONAL_PENSION_ESTIMATE_HEADER, "").strip()
    employee_raw = settings.get(EMPLOYEE_PENSION_ESTIMATE_HEADER, "").strip()
    claim_timing_raw = settings.get(PENSION_CLAIM_TIMING_HEADER, "").strip()
    claim_age_raw = settings.get(PENSION_CLAIM_AGE_HEADER, "").strip()

    national_amount = (
        _parse_money(national_raw, f"{PLAN_SHEET}!{NATIONAL_PENSION_ESTIMATE_HEADER}")
        if national_raw
        else Money.zero()
    )
    employee_amount = (
        _parse_money(employee_raw, f"{PLAN_SHEET}!{EMPLOYEE_PENSION_ESTIMATE_HEADER}")
        if employee_raw
        else Money.zero()
    )
    claim_timing_type = (
        _parse_enum(ClaimTimingType, claim_timing_raw, f"{PLAN_SHEET}!{PENSION_CLAIM_TIMING_HEADER}")
        if claim_timing_raw
        else ClaimTimingType.STANDARD
    )
    claim_age = _parse_int(claim_age_raw, f"{PLAN_SHEET}!{PENSION_CLAIM_AGE_HEADER}") if claim_age_raw else 65

    return Pension(
        national_pension=PensionEntitlement(estimate_annual=national_amount),
        employee_pension=PensionEntitlement(estimate_annual=employee_amount),
        claim_timing=ClaimTiming(timing_type=claim_timing_type, age=claim_age),
    )


def _build_milestones(settings: dict[str, str]) -> list[Milestone]:
    """入力_プラン設定のシミュレーション終了年齢（RETIREMENT_AGE_HEADER、任意入力）から
    RETIREMENTマイルストーンを組み立てる。

    この値は収入を止める機能ではなく、シミュレーション期間をどこまで計算するかだけを制御する
    （未入力なら30年間、入力するとその年齢に達する年以降・想定寿命まで自動延長する。
    既存のprojection_engine._resolve_end_yearのロジック）。給与収入等がいつ止まるかは
    入力_収入の終了条件タイプ/値で個別に設定する。
    """

    retirement_age_raw = settings.get(RETIREMENT_AGE_HEADER, "").strip()
    if not retirement_age_raw:
        return []

    age = _parse_int(retirement_age_raw, f"{PLAN_SHEET}!{RETIREMENT_AGE_HEADER}")
    return [
        Milestone(
            milestone_id="milestone_retirement",
            milestone_type=MilestoneType.RETIREMENT,
            trigger=EventCondition.at_age(age),
        )
    ]


def _build_life_expectancy_age(settings: dict[str, str]) -> int:
    """入力_プラン設定の想定寿命（任意入力）を読み込む。未入力ならDEFAULT_LIFE_EXPECTANCY_AGE(100歳)。"""

    raw = settings.get(LIFE_EXPECTANCY_HEADER, "").strip()
    if not raw:
        return DEFAULT_LIFE_EXPECTANCY_AGE
    return _parse_int(raw, f"{PLAN_SHEET}!{LIFE_EXPECTANCY_HEADER}")


def read_target_ending_networth(spreadsheet: gspread.Spreadsheet) -> Money:
    """入力_プラン設定の目標資産（想定寿命時点、任意入力）を読み込む。未入力なら0円。

    ダッシュボードの逆算機能でのみ使う値のため、Plan Aggregateには含めない。
    """

    settings = _read_plan_settings(spreadsheet)
    raw = settings.get(TARGET_ENDING_NETWORTH_HEADER, "").strip()
    if not raw:
        return Money.zero()
    return _parse_money(raw, f"{PLAN_SHEET}!{TARGET_ENDING_NETWORTH_HEADER}")


def _default_withdrawal_strategy() -> WithdrawalStrategy:
    return WithdrawalStrategy(
        order=[
            AccountType.CASH,
            AccountType.TAXABLE,
            AccountType.NISA_GROWTH,
            AccountType.NISA_TSUMITATE,
            AccountType.ZAIKEI,
            AccountType.IDECO,
            AccountType.COMPANY_DC,
        ]
    )


def _default_contribution_strategy() -> ContributionStrategy:
    return ContributionStrategy(
        order=[
            AccountType.CASH,
            AccountType.NISA_GROWTH,
            AccountType.NISA_TSUMITATE,
            AccountType.IDECO,
            AccountType.COMPANY_DC,
            AccountType.ZAIKEI,
            AccountType.TAXABLE,
        ],
        emergency_fund_target=Money.of(1_000_000),
    )


def build_plan_from_spreadsheet(spreadsheet: gspread.Spreadsheet) -> Plan:
    settings = _read_plan_settings(spreadsheet)
    user = _build_user(settings)
    assumptions = _build_assumptions(settings)
    expenses, one_time_expenses = _build_expenses(spreadsheet, assumptions.inflation_rate)
    children, education_expenses = _build_children_and_education_expenses(spreadsheet)

    return Plan(
        plan_id=_require_setting(settings, PLAN_ID_HEADER),
        name=_require_setting(settings, PLAN_NAME_HEADER),
        user=user,
        start_condition=StartCondition(StartConditionType.TODAY),
        assumptions=assumptions,
        accounts=_build_accounts(spreadsheet),
        tax_config=_default_tax_config(),
        pension=_build_pension(settings),
        withdrawal_strategy=_default_withdrawal_strategy(),
        contribution_strategy=_default_contribution_strategy(),
        incomes=_build_incomes(spreadsheet, assumptions.inflation_rate),
        expenses=expenses,
        milestones=_build_milestones(settings),
        allocation_policy=_build_allocation_policy(spreadsheet),
        children=children,
        education_expenses=education_expenses,
        one_time_expenses=one_time_expenses,
        life_expectancy_age=_build_life_expectancy_age(settings),
    )


@dataclass
class InputWarning:
    """入力ミスではないが、実行時に無視される入力値（設定の組み合わせ次第で使われない列に
    値が入っている等）。StructuralInputErrorと違い実行は止めない（設計書11章の「警告」に相当）。
    """

    field_path: str
    message: str


def collect_input_warnings(spreadsheet: gspread.Spreadsheet) -> list[InputWarning]:
    """実行時に無視される入力値を検出する（実行は止めず、出力_エラーシートへの警告表示に使う）。

    - 入力_支出: 単発フラグ=TRUEの行では成長率が使われない。
      単発フラグ=FALSEの行では開始条件タイプ/値が使われない。
    - 入力_収入: 終了条件タイプが未入力だと終了条件値があっても終了条件自体が設定されない
      （_build_event_conditionはtypeが空なら値を見ずにNoneを返すため）。
    """

    warnings: list[InputWarning] = []
    warnings.extend(_collect_expenses_warnings(spreadsheet))
    warnings.extend(_collect_incomes_warnings(spreadsheet))
    return warnings


_UNUSED_WHEN_ONE_TIME = (GROWTH_RATE_HEADER, AMOUNT_ANNUAL_HEADER)
_UNUSED_WHEN_RECURRING = (START_TYPE_HEADER, START_VALUE_HEADER, ONE_TIME_AMOUNT_HEADER)


def _collect_expenses_warnings(spreadsheet: gspread.Spreadsheet) -> list[InputWarning]:
    try:
        worksheet = spreadsheet.worksheet(EXPENSES_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        return []

    warnings = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{EXPENSES_SHEET}!row{row_number}"
        is_one_time = _parse_bool(record.get(ONE_TIME_FLAG_HEADER, "FALSE"))
        unused_headers = _UNUSED_WHEN_ONE_TIME if is_one_time else _UNUSED_WHEN_RECURRING
        flag_value = "TRUE" if is_one_time else "FALSE"
        for header in unused_headers:
            if str(record.get(header, "")).strip():
                warnings.append(
                    InputWarning(
                        f"{row_prefix}.{header}",
                        f"{ONE_TIME_FLAG_HEADER}={flag_value}の行では{header}は使われません（無視されます）",
                    )
                )
    return warnings


def _collect_incomes_warnings(spreadsheet: gspread.Spreadsheet) -> list[InputWarning]:
    try:
        worksheet = spreadsheet.worksheet(INCOMES_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        return []

    warnings = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{INCOMES_SHEET}!row{row_number}"
        end_type_raw = str(record.get(END_TYPE_HEADER, "")).strip()
        end_value_raw = str(record.get(END_VALUE_HEADER, "")).strip()
        if end_value_raw and not end_type_raw:
            warnings.append(
                InputWarning(
                    f"{row_prefix}.{END_VALUE_HEADER}",
                    f"{END_TYPE_HEADER}が未入力のため、{END_VALUE_HEADER}は使われません（終了条件なしとして扱われます）",
                )
            )
    return warnings


def load_plan(
    spreadsheet_name: str = SPREADSHEET_NAME,
    credentials_path: str = DEFAULT_CREDENTIALS_PATH,
) -> Plan:
    client = build_client(credentials_path)
    spreadsheet = open_spreadsheet(client, spreadsheet_name)
    return build_plan_from_spreadsheet(spreadsheet)


def load_portfolios(
    spreadsheet_name: str = SPREADSHEET_NAME,
    credentials_path: str = DEFAULT_CREDENTIALS_PATH,
) -> dict[str, Portfolio]:
    client = build_client(credentials_path)
    spreadsheet = open_spreadsheet(client, spreadsheet_name)
    return build_portfolios_from_spreadsheet(spreadsheet)


def load_scenarios(
    plan_id: str,
    spreadsheet_name: str = SPREADSHEET_NAME,
    credentials_path: str = DEFAULT_CREDENTIALS_PATH,
) -> list[Scenario]:
    client = build_client(credentials_path)
    spreadsheet = open_spreadsheet(client, spreadsheet_name)
    return build_scenarios_from_spreadsheet(spreadsheet, plan_id)


def load_progress_records(
    spreadsheet_name: str = SPREADSHEET_NAME,
    credentials_path: str = DEFAULT_CREDENTIALS_PATH,
) -> list[ProgressRecord]:
    client = build_client(credentials_path)
    spreadsheet = open_spreadsheet(client, spreadsheet_name)
    return build_progress_records_from_spreadsheet(spreadsheet)


def load_target_ending_networth(
    spreadsheet_name: str = SPREADSHEET_NAME,
    credentials_path: str = DEFAULT_CREDENTIALS_PATH,
) -> Money:
    client = build_client(credentials_path)
    spreadsheet = open_spreadsheet(client, spreadsheet_name)
    return read_target_ending_networth(spreadsheet)
