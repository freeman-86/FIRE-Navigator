from __future__ import annotations

from datetime import date, datetime
from decimal import InvalidOperation
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from adapters.sheets.sheet_mapping import (
    ACCOUNTS_SHEET,
    EXPENSES_SHEET,
    INCOMES_SHEET,
    PLAN_SHEET,
    PROGRESS_SHEET,
    SCENARIOS_SHEET,
    SPREADSHEET_NAME,
)
from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset, AssetClass
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.errors import StructuralInputError
from core.domain.expense import Expense
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.progress_record import ProgressRecord
from core.domain.scenario import Scenario
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy

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
        return Money.of(value)
    except (InvalidOperation, ValueError, TypeError) as e:
        raise StructuralInputError(f"金額として解釈できない値です: {value!r}", field_path) from e


def _parse_rate(value: object, field_path: str) -> Rate:
    try:
        return Rate.of(value)
    except (InvalidOperation, ValueError, TypeError) as e:
        raise StructuralInputError(f"割合として解釈できない値です: {value!r}", field_path) from e


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
        raise StructuralInputError(f"必須項目が未入力です（{PLAN_SHEET}のA列に'{key}'の行がないか、B列が空です）", f"{PLAN_SHEET}!{key}")
    return value


def _build_user(settings: dict[str, str]) -> User:
    return User(
        birth_date=_parse_date_field(_require_setting(settings, "birth_date"), f"{PLAN_SHEET}!birth_date"),
        residence=_parse_enum(Prefecture, _require_setting(settings, "residence"), f"{PLAN_SHEET}!residence"),
    )


def _build_assumptions(settings: dict[str, str]) -> Assumptions:
    return Assumptions(
        inflation_rate=_parse_rate(_require_setting(settings, "inflation_rate"), f"{PLAN_SHEET}!inflation_rate"),
        investment_growth_rate=_parse_rate(
            _require_setting(settings, "investment_growth_rate"), f"{PLAN_SHEET}!investment_growth_rate"
        ),
    )


def _build_accounts(spreadsheet: gspread.Spreadsheet) -> list[Account]:
    worksheet = spreadsheet.worksheet(ACCOUNTS_SHEET)
    accounts = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{ACCOUNTS_SHEET}!row{row_number}"
        account_id = str(_require(record, "account_id", f"{row_prefix}.account_id"))
        monthly_contribution_raw = str(record.get("monthly_contribution", "")).strip()
        accounts.append(
            Account(
                account_id=account_id,
                account_type=_parse_enum(
                    AccountType, _require(record, "account_type", f"{row_prefix}.account_type"), f"{row_prefix}.account_type"
                ),
                owner=_parse_enum(OwnerType, _require(record, "owner", f"{row_prefix}.owner"), f"{row_prefix}.owner"),
                monthly_contribution=(
                    _parse_money(monthly_contribution_raw, f"{row_prefix}.monthly_contribution")
                    if monthly_contribution_raw
                    else None
                ),
            )
        )
    return accounts


def _build_portfolios(spreadsheet: gspread.Spreadsheet) -> dict[str, Portfolio]:
    """Portfolio Aggregate（account_idで参照される独立集約）をInput_Accountsシートから組み立てる。"""

    worksheet = spreadsheet.worksheet(ACCOUNTS_SHEET)
    portfolios: dict[str, Portfolio] = {}
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{ACCOUNTS_SHEET}!row{row_number}"
        account_id = str(_require(record, "account_id", f"{row_prefix}.account_id"))
        asset = Asset(
            asset_class=_parse_enum(
                AssetClass, _require(record, "asset_class", f"{row_prefix}.asset_class"), f"{row_prefix}.asset_class"
            ),
            expected_return=_parse_rate(
                _require(record, "expected_return", f"{row_prefix}.expected_return"), f"{row_prefix}.expected_return"
            ),
            volatility=_parse_rate(
                _require(record, "volatility", f"{row_prefix}.volatility"), f"{row_prefix}.volatility"
            ),
        )
        holding = Holding(
            asset=asset,
            quantity=1,
            cost_basis=_parse_money(_require(record, "balance", f"{row_prefix}.balance"), f"{row_prefix}.balance"),
        )
        portfolios[account_id] = Portfolio(holdings=[holding])
    return portfolios


def _build_scenarios(spreadsheet: gspread.Spreadsheet, plan_id: str) -> list[Scenario]:
    """Scenario Aggregate（plan_idで参照される独立集約）をInput_Scenariosシートから組み立てる。

    Input_Scenariosシートが存在しない場合は空リストを返す（シナリオ比較はオプション機能）。
    """

    try:
        worksheet = spreadsheet.worksheet(SCENARIOS_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        return []

    scenarios = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{SCENARIOS_SHEET}!row{row_number}"
        overrides = {}
        retirement_age_raw = str(record.get("retirement_age", "")).strip()
        if retirement_age_raw:
            overrides["retirement_age"] = _parse_int(retirement_age_raw, f"{row_prefix}.retirement_age")
        scenarios.append(
            Scenario(
                scenario_id=str(_require(record, "scenario_id", f"{row_prefix}.scenario_id")),
                plan_id=plan_id,
                name=str(_require(record, "name", f"{row_prefix}.name")),
                overrides=overrides,
            )
        )
    return scenarios


def _build_progress_records(spreadsheet: gspread.Spreadsheet) -> list[ProgressRecord]:
    """実績ネットワースをInput_Progressシートから読み込む。

    Input_Progressシートが存在しない場合は空リストを返す（Progress比較はオプション機能）。
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
                year=_parse_int(_require(record, "year", f"{row_prefix}.year"), f"{row_prefix}.year"),
                actual_networth=_parse_money(
                    _require(record, "actual_networth", f"{row_prefix}.actual_networth"), f"{row_prefix}.actual_networth"
                ),
            )
        )
    return records


def _build_incomes(spreadsheet: gspread.Spreadsheet) -> list[Income]:
    worksheet = spreadsheet.worksheet(INCOMES_SHEET)
    incomes = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{INCOMES_SHEET}!row{row_number}"
        start_condition = _build_event_condition(
            record.get("start_type"), record.get("start_value"), f"{row_prefix}.start_type"
        )
        if start_condition is None:
            raise StructuralInputError("start_typeが必須です", f"{row_prefix}.start_type")
        end_condition = _build_event_condition(record.get("end_type"), record.get("end_value"), f"{row_prefix}.end_type")
        incomes.append(
            Income(
                income_id=str(_require(record, "income_id", f"{row_prefix}.income_id")),
                source=str(_require(record, "source", f"{row_prefix}.source")),
                amount=_parse_money(
                    _require(record, "amount_annual", f"{row_prefix}.amount_annual"), f"{row_prefix}.amount_annual"
                ),
                growth_rate=_parse_rate(
                    _require(record, "growth_rate", f"{row_prefix}.growth_rate"), f"{row_prefix}.growth_rate"
                ),
                start_condition=start_condition,
                end_condition=end_condition,
            )
        )
    return incomes


def _build_expenses(spreadsheet: gspread.Spreadsheet) -> list[Expense]:
    worksheet = spreadsheet.worksheet(EXPENSES_SHEET)
    expenses = []
    for row_number, record in enumerate(worksheet.get_all_records(), start=2):
        row_prefix = f"{EXPENSES_SHEET}!row{row_number}"
        expenses.append(
            Expense(
                expense_id=str(_require(record, "expense_id", f"{row_prefix}.expense_id")),
                category=str(_require(record, "category", f"{row_prefix}.category")),
                amount=_parse_money(
                    _require(record, "amount_annual", f"{row_prefix}.amount_annual"), f"{row_prefix}.amount_annual"
                ),
                growth_rate=_parse_rate(
                    _require(record, "growth_rate", f"{row_prefix}.growth_rate"), f"{row_prefix}.growth_rate"
                ),
                is_flexible=_parse_bool(record.get("is_flexible", "FALSE")),
            )
        )
    return expenses


def _default_tax_config(user: User) -> TaxConfig:
    return TaxConfig(residence=user.residence)


def _default_pension() -> Pension:
    return Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )


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

    return Plan(
        plan_id=_require_setting(settings, "plan_id"),
        name=_require_setting(settings, "name"),
        user=user,
        start_condition=StartCondition(StartConditionType.TODAY),
        assumptions=_build_assumptions(settings),
        accounts=_build_accounts(spreadsheet),
        tax_config=_default_tax_config(user),
        pension=_default_pension(),
        withdrawal_strategy=_default_withdrawal_strategy(),
        contribution_strategy=_default_contribution_strategy(),
        incomes=_build_incomes(spreadsheet),
        expenses=_build_expenses(spreadsheet),
    )


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
    return _build_portfolios(spreadsheet)


def load_scenarios(
    plan_id: str,
    spreadsheet_name: str = SPREADSHEET_NAME,
    credentials_path: str = DEFAULT_CREDENTIALS_PATH,
) -> list[Scenario]:
    client = build_client(credentials_path)
    spreadsheet = open_spreadsheet(client, spreadsheet_name)
    return _build_scenarios(spreadsheet, plan_id)


def load_progress_records(
    spreadsheet_name: str = SPREADSHEET_NAME,
    credentials_path: str = DEFAULT_CREDENTIALS_PATH,
) -> list[ProgressRecord]:
    client = build_client(credentials_path)
    spreadsheet = open_spreadsheet(client, spreadsheet_name)
    return _build_progress_records(spreadsheet)
