from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from core.domain.expense import Expense
from core.domain.income import Income
from core.domain.milestone import MilestoneType
from core.domain.plan import Plan, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.portfolio_rules import PortfolioRules
from core.domain.simulation_result import SimulationResult, YearlyProjection
from core.domain.tax_config import TaxRules
from core.domain.value_objects import EventCondition, Money, Rate
from core.simulation.portfolio.portfolio_engine import allocate_discretionary_surplus, plan_fixed_contributions
from core.simulation.projection.event_conditions import resolve_condition_year
from core.simulation.projection.milestone_evaluation import evaluate_milestones
from core.simulation.tax.tax_engine import calculate_tax

DEFAULT_PROJECTION_YEARS = 30
UNALLOCATED_SURPLUS_KEY = "unallocated_surplus"


def run_projection(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
) -> SimulationResult:
    """決定論的シミュレーション。手取り収入から確定拠出(iDeCo/DC等)と生活費を差し引いた裁量的余剰を、
    contribution_strategyの優先順位で口座へ自動配分しながら年次ネットワース推移を計算する。

    portfolios/tax_rules/portfolio_rulesはApplication層相当の呼び出し元が用意して渡す。
    Portfolio AggregateはPlan Aggregateから独立しており、account_idをキーに参照する
    （設計書v1.1 ② Aggregateの見直し）。Simulation Engineはyaml等のI/Oを直接扱わない
    （設計書3.2 依存方向の原則）。
    """

    start_year = _resolve_start_year(plan)
    end_year = _resolve_end_year(plan, start_year)
    growth_rate = plan.assumptions.investment_growth_rate
    birth_date = plan.user.birth_date
    has_spouse = plan.user.spouse is not None

    account_balances = {
        account.account_id: _initial_balance(portfolios.get(account.account_id)) for account in plan.accounts
    }
    lifetime_contributions = {account.account_id: Money.zero() for account in plan.accounts}
    surplus_reserve = Money.zero()

    yearly_projections: list[YearlyProjection] = []
    for offset, year in enumerate(range(start_year, end_year + 1)):
        gross_income = _active_income_total(plan.incomes, year, start_year, birth_date, offset)
        total_expense = _expense_total(plan.expenses, offset)

        fixed_plan = plan_fixed_contributions(plan.accounts, lifetime_contributions, portfolio_rules)
        tax_result = calculate_tax(
            gross_income, plan.tax_config, has_spouse, tax_rules, fixed_plan.tax_deductible_amount
        )
        net_cashflow = tax_result.net_income - total_expense
        discretionary_surplus = net_cashflow - _total(fixed_plan.contributions)

        discretionary_contributions, unallocated_leftover = allocate_discretionary_surplus(
            plan.accounts,
            account_balances,
            lifetime_contributions,
            fixed_plan.contributions,
            discretionary_surplus,
            plan.contribution_strategy,
            portfolio_rules,
        )
        contributions_this_year = _merge(fixed_plan.contributions, discretionary_contributions)

        # 配分しきれなかった余剰、および赤字(discretionary_surplusが負)はこれまで通りunallocated_surplusで吸収する
        unallocated_delta = unallocated_leftover
        if discretionary_surplus.is_negative:
            unallocated_delta = unallocated_delta + discretionary_surplus

        account_balances = {
            account_id: _grow(balance, growth_rate) + contributions_this_year.get(account_id, Money.zero())
            for account_id, balance in account_balances.items()
        }
        lifetime_contributions = {
            account_id: lifetime_contributions[account_id] + contributions_this_year.get(account_id, Money.zero())
            for account_id in lifetime_contributions
        }
        surplus_reserve = _grow(surplus_reserve, growth_rate) + unallocated_delta

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

    milestone_outcomes = evaluate_milestones(plan, yearly_projections)

    return SimulationResult(yearly_projections=yearly_projections, milestone_outcomes=milestone_outcomes)


def _initial_balance(portfolio: Optional[Portfolio]) -> Money:
    if portfolio is None:
        return Money.zero()
    total = Money.zero()
    for holding in portfolio.holdings:
        total = total + holding.cost_basis
    return total


def _total(amounts: dict[str, Money]) -> Money:
    total = Money.zero()
    for amount in amounts.values():
        total = total + amount
    return total


def _merge(a: dict[str, Money], b: dict[str, Money]) -> dict[str, Money]:
    merged = dict(a)
    for account_id, amount in b.items():
        merged[account_id] = merged.get(account_id, Money.zero()) + amount
    return merged


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
            return resolve_condition_year(milestone.trigger, start_year, plan.user.birth_date)
    return None


def _is_active(
    start_condition: EventCondition,
    end_condition: Optional[EventCondition],
    year: int,
    start_year: int,
    birth_date: date,
) -> bool:
    start_year_resolved = resolve_condition_year(start_condition, start_year, birth_date)
    if start_year_resolved is not None and year < start_year_resolved:
        return False
    if end_condition is not None:
        end_year_resolved = resolve_condition_year(end_condition, start_year, birth_date)
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
