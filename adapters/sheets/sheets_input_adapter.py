from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from adapters.sheets.sheet_mapping import (
    ACCOUNTS_SHEET,
    EXPENSES_SHEET,
    INCOMES_SHEET,
    PLAN_SHEET,
    SPREADSHEET_NAME,
)
from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset, AssetClass
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.expense import Expense
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
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


def _parse_bool(value: object) -> bool:
    return str(value).strip().upper() in ("TRUE", "1", "YES")


def _parse_date(value: object) -> date:
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def _build_event_condition(condition_type: object, value: object) -> Optional[EventCondition]:
    normalized_type = str(condition_type or "").strip().lower()
    normalized_value = str(value or "").strip()
    if normalized_type in ("", "none"):
        return None
    if normalized_type == "today":
        return EventCondition.today()
    if normalized_type == "plan_start":
        return EventCondition.plan_start()
    if normalized_type == "age":
        return EventCondition.at_age(int(normalized_value))
    if normalized_type == "date":
        return EventCondition.at_date(_parse_date(normalized_value))
    raise ValueError(f"未知のcondition_type: {normalized_type}")


def _read_plan_settings(spreadsheet: gspread.Spreadsheet) -> dict[str, str]:
    worksheet = spreadsheet.worksheet(PLAN_SHEET)
    rows = worksheet.get_all_values()
    return {row[0]: row[1] for row in rows if row and row[0]}


def _build_user(settings: dict[str, str]) -> User:
    return User(
        birth_date=_parse_date(settings["birth_date"]),
        residence=Prefecture(settings["residence"]),
    )


def _build_assumptions(settings: dict[str, str]) -> Assumptions:
    return Assumptions(
        inflation_rate=Rate.of(settings["inflation_rate"]),
        investment_growth_rate=Rate.of(settings["investment_growth_rate"]),
    )


def _build_accounts(spreadsheet: gspread.Spreadsheet) -> list[Account]:
    worksheet = spreadsheet.worksheet(ACCOUNTS_SHEET)
    accounts = []
    for record in worksheet.get_all_records():
        asset = Asset(
            asset_class=AssetClass(record["asset_class"]),
            expected_return=Rate.of(record["expected_return"]),
            volatility=Rate.of(record["volatility"]),
        )
        holding = Holding(asset=asset, quantity=1, cost_basis=Money.of(record["balance"]))
        monthly_contribution_raw = str(record.get("monthly_contribution", "")).strip()
        accounts.append(
            Account(
                account_id=str(record["account_id"]),
                account_type=AccountType(record["account_type"]),
                owner=OwnerType(record["owner"]),
                portfolio=Portfolio(holdings=[holding]),
                monthly_contribution=Money.of(monthly_contribution_raw) if monthly_contribution_raw else None,
            )
        )
    return accounts


def _build_incomes(spreadsheet: gspread.Spreadsheet) -> list[Income]:
    worksheet = spreadsheet.worksheet(INCOMES_SHEET)
    incomes = []
    for record in worksheet.get_all_records():
        start_condition = _build_event_condition(record.get("start_type"), record.get("start_value"))
        if start_condition is None:
            raise ValueError(f"income_id={record.get('income_id')} には start_type が必須です")
        end_condition = _build_event_condition(record.get("end_type"), record.get("end_value"))
        incomes.append(
            Income(
                income_id=str(record["income_id"]),
                source=str(record["source"]),
                amount=Money.of(record["amount_annual"]),
                growth_rate=Rate.of(record["growth_rate"]),
                start_condition=start_condition,
                end_condition=end_condition,
            )
        )
    return incomes


def _build_expenses(spreadsheet: gspread.Spreadsheet) -> list[Expense]:
    worksheet = spreadsheet.worksheet(EXPENSES_SHEET)
    return [
        Expense(
            expense_id=str(record["expense_id"]),
            category=str(record["category"]),
            amount=Money.of(record["amount_annual"]),
            growth_rate=Rate.of(record["growth_rate"]),
            is_flexible=_parse_bool(record.get("is_flexible", "FALSE")),
        )
        for record in worksheet.get_all_records()
    ]


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
            AccountType.IDECO,
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
        plan_id=settings["plan_id"],
        name=settings["name"],
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
