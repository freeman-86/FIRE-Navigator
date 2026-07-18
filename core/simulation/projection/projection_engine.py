from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from core.domain.account import Account
from core.domain.expense import Expense
from core.domain.income import Income
from core.domain.milestone import MilestoneType
from core.domain.plan import Plan, StartConditionType
from core.domain.simulation_result import SimulationResult, YearlyProjection
from core.domain.tax_config import TaxRules
from core.domain.value_objects import EventCondition, EventConditionType, Money, Rate
from core.simulation.tax.tax_engine import calculate_tax

DEFAULT_PROJECTION_YEARS = 30
UNALLOCATED_SURPLUS_KEY = "unallocated_surplus"


def run_projection(plan: Plan, tax_rules: TaxRules) -> SimulationResult:
    """決定論的シミュレーション。収入(手取りベース)-支出=余剰、資産×成長率で年次ネットワース推移を計算する（Sprint5スコープ）。

    tax_rulesはApplication層相当の呼び出し元がrepositories.config_repository.load_tax_rules()等で
    用意して渡す。Simulation Engineはyaml等のI/Oを直接扱わない（設計書3.2 依存方向の原則）。
    """

    start_year = _resolve_start_year(plan)
    end_year = _resolve_end_year(plan, start_year)
    growth_rate = plan.assumptions.investment_growth_rate
    birth_date = plan.user.birth_date
    has_spouse = plan.user.spouse is not None

    account_balances = {account.account_id: _initial_balance(account) for account in plan.accounts}
    surplus_reserve = Money.zero()

    yearly_projections: list[YearlyProjection] = []
    for offset, year in enumerate(range(start_year, end_year + 1)):
        gross_income = _active_income_total(plan.incomes, year, start_year, birth_date, offset)
        total_expense = _expense_total(plan.expenses, offset)

        tax_result = calculate_tax(gross_income, plan.tax_config, has_spouse, tax_rules)
        net_cashflow = tax_result.net_income - total_expense

        account_balances = {
            account_id: _grow(balance, growth_rate) for account_id, balance in account_balances.items()
        }
        surplus_reserve = _grow(surplus_reserve, growth_rate) + net_cashflow

        balances_snapshot = {**account_balances, UNALLOCATED_SURPLUS_KEY: surplus_reserve}
        networth = sum(balances_snapshot.values(), Money.zero())

        yearly_projections.append(
            YearlyProjection(
                year=year,
                age_self=year - birth_date.year,
                gross_income=gross_income,
                income_tax=tax_result.income_tax,
                resident_tax=tax_result.resident_tax,
                social_insurance=tax_result.social_insurance,
                net_income=tax_result.net_income,
                total_expense=total_expense,
                net_cashflow=net_cashflow,
                account_balances=balances_snapshot,
                networth=networth,
            )
        )

    return SimulationResult(yearly_projections=yearly_projections)


def _initial_balance(account: Account) -> Money:
    total = Money.zero()
    for holding in account.portfolio.holdings:
        total = total + holding.cost_basis
    return total


def _grow(money: Money, rate: Rate) -> Money:
    return money + rate.apply_to(money)


def _grown_amount(amount: Money, growth_rate: Rate, offset: int) -> Money:
    factor = (Decimal(1) + growth_rate.value) ** offset
    return amount * factor


def _resolve_start_year(plan: Plan) -> int:
    condition = plan.start_condition
    if condition.condition_type == StartConditionType.FIXED_DATE:
        return condition.fixed_date.year
    return date.today().year


def _resolve_end_year(plan: Plan, start_year: int) -> int:
    retirement_year = _retirement_year(plan, start_year)
    if retirement_year is not None:
        return max(retirement_year, start_year)
    return start_year + DEFAULT_PROJECTION_YEARS - 1


def _retirement_year(plan: Plan, start_year: int) -> Optional[int]:
    for milestone in plan.milestones:
        if milestone.milestone_type == MilestoneType.RETIREMENT:
            return _condition_year(milestone.trigger, start_year, plan.user.birth_date)
    return None


def _condition_year(condition: EventCondition, start_year: int, birth_date: date) -> Optional[int]:
    if condition.condition_type in (EventConditionType.TODAY, EventConditionType.PLAN_START):
        return start_year
    if condition.condition_type in (EventConditionType.DATE, EventConditionType.FIXED_DATE):
        return condition.date.year
    if condition.condition_type == EventConditionType.AGE:
        return birth_date.year + condition.age
    # networth_multiple_of_expense等、年次カレンダーだけでは解決できない条件はSprint3では未対応
    return None


def _is_active(
    start_condition: EventCondition,
    end_condition: Optional[EventCondition],
    year: int,
    start_year: int,
    birth_date: date,
) -> bool:
    start_year_resolved = _condition_year(start_condition, start_year, birth_date)
    if start_year_resolved is not None and year < start_year_resolved:
        return False
    if end_condition is not None:
        end_year_resolved = _condition_year(end_condition, start_year, birth_date)
        if end_year_resolved is not None and year >= end_year_resolved:
            return False
    return True


def _active_income_total(
    incomes: list[Income], year: int, start_year: int, birth_date: date, offset: int
) -> Money:
    total = Money.zero()
    for income in incomes:
        if not _is_active(income.start_condition, income.end_condition, year, start_year, birth_date):
            continue
        total = total + _grown_amount(income.amount, income.growth_rate, offset)
    return total


def _expense_total(expenses: list[Expense], offset: int) -> Money:
    total = Money.zero()
    for expense in expenses:
        total = total + _grown_amount(expense.amount, expense.growth_rate, offset)
    return total
