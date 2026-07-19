from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable, Optional

from core.domain.asset import AssetClass
from core.domain.child import Child
from core.domain.education_expense import EducationExpenseBand
from core.domain.expense import Expense
from core.domain.income import Income
from core.domain.milestone import MilestoneType
from core.domain.one_time_expense import OneTimeExpense
from core.domain.pension import PensionRules
from core.domain.plan import Plan, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.portfolio_rules import PortfolioRules
from core.domain.simulation_result import MonthlyProjection, SimulationResult, YearlyProjection
from core.domain.tax_config import TaxRules
from core.domain.value_objects import EventCondition, Money, Rate
from core.simulation.pension.pension_engine import calculate_pension_income
from core.simulation.portfolio.portfolio_engine import allocate_discretionary_surplus, plan_fixed_contributions
from core.simulation.portfolio.rebalance_engine import rebalance
from core.simulation.projection.event_conditions import resolve_condition_month, resolve_condition_year
from core.simulation.projection.milestone_evaluation import evaluate_milestones
from core.simulation.tax.tax_engine import calculate_tax
from core.simulation.withdrawal.withdrawal_engine import withdraw_shortfall

DEFAULT_PROJECTION_YEARS = 30
DEFAULT_LIFE_EXPECTANCY_AGE = 100
UNALLOCATED_SURPLUS_KEY = "unallocated_surplus"
MONTHS_PER_YEAR = 12


def run_projection(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
    pension_rules: PensionRules,
    growth_rate_provider: Optional[Callable[[int], Rate]] = None,
) -> SimulationResult:
    """決定論的シミュレーション。内部的には月次ループで計算し（Sprint12 月次化）、
    年末時点のスナップショットを従来通りYearlyProjectionとして積み上げる。これにより
    milestone評価・感応度分析・チャート・Monte Carlo/Historical Engine等の年次インターフェースは
    無改修で動作する。月次の明細はSimulationResult.monthly_projectionsに別途保持する。

    退職(RETIREMENT)マイルストーンがある場合、想定寿命(DEFAULT_LIFE_EXPECTANCY_AGE)まで
    退職後フェーズを含めて計算する。手取り収入(給与+年金)が生活費・確定拠出を上回る月は
    contribution_strategyの優先順位で口座へ自動配分し、下回る月（退職後の取り崩し局面等）は
    withdrawal_strategyの優先順位で口座残高を取り崩す。

    所得税・住民税・社会保険料は日本の税制がそもそも年次確定であるため、従来通り年1回のみ
    計算し、その結果を12等分して毎月のキャッシュフローに反映する（旧ドラフトのEngineと同様の
    簡略化）。収入・支出の開始/終了条件は現時点では年単位でのみ判定する（月単位への精緻化は
    将来課題）。

    portfolios/tax_rules/portfolio_rules/pension_rulesはApplication層相当の呼び出し元が
    用意して渡す。Simulation Engineはyaml等のI/Oを直接扱わない（設計書3.2 依存方向の原則）。

    growth_rate_provider: 月次オフセット(0始まり)を受け取りその月の資産成長率を返す関数。
    省略時はplan.assumptions.investment_growth_rate（年率固定値）をmonthly_equivalent()で
    月率に変換し、毎月同じ値を使う従来通りの決定論的計算になる。Monte Carlo Engineは毎月
    新規にサンプリングした相関考慮済みの月次リターンを、Historical Engineは実績の年次リターンを
    月率換算した値を返す関数をここに渡すことで、同じProjection Engineを反復実行する
    （設計書v1.1 ⑥⑦）。
    """

    start_year = resolve_start_year(plan)
    start_month = resolve_start_month(plan)
    end_year = _resolve_end_year(plan, start_year)
    birth_date = plan.user.birth_date
    has_spouse = plan.user.spouse is not None
    default_monthly_rate = plan.assumptions.investment_growth_rate.monthly_equivalent()
    one_time_expenses_by_month_offset = _one_time_expenses_by_month_offset(
        plan.one_time_expenses, start_year, start_month, birth_date
    )

    account_balances = {
        account.account_id: _initial_balance(portfolios.get(account.account_id)) for account in plan.accounts
    }
    # 取り崩し時の譲渡税計算（平均取得原価方式）に使う累計取得原価。シミュレーション開始時点の
    # 残高をそのまま初期取得原価とする（開始前の含み益は追跡しない簡易化）。
    cost_basis_balances = dict(account_balances)
    lifetime_contributions = {account.account_id: Money.zero() for account in plan.accounts}
    surplus_reserve = Money.zero()
    asset_class_by_account_id = _asset_class_by_account_id(portfolios)

    yearly_projections: list[YearlyProjection] = []
    monthly_projections: list[MonthlyProjection] = []
    for offset_year, year in enumerate(range(start_year, end_year + 1)):
        age = year - birth_date.year
        gross_income_annual = _active_income_total(plan.incomes, year, start_year, birth_date, offset_year)
        pension_income_annual = calculate_pension_income(age, plan.pension, pension_rules)
        education_expense_monthly = _education_expense_monthly_total(plan.children, plan.education_expenses, year)
        total_expense_annual = _expense_total(plan.expenses, offset_year) + education_expense_monthly * 12

        fixed_plan = plan_fixed_contributions(plan.accounts, lifetime_contributions, portfolio_rules)
        tax_result = calculate_tax(
            gross_income_annual, pension_income_annual, plan.tax_config, has_spouse, tax_rules,
            fixed_plan.tax_deductible_amount,
        )

        monthly_gross_income = _divide_by_12(gross_income_annual)
        monthly_pension_income = _divide_by_12(pension_income_annual)
        monthly_net_income = _divide_by_12(tax_result.net_income)
        monthly_recurring_expense = _divide_by_12(total_expense_annual)
        monthly_fixed_contributions = {
            account_id: _divide_by_12(amount) for account_id, amount in fixed_plan.contributions.items()
        }
        discretionary_contributed_this_year: dict[str, Money] = {}
        capital_gains_tax_annual = Money.zero()
        one_time_expense_annual = Money.zero()

        balances_snapshot: dict[str, Money] = {}
        networth = Money.zero()
        for month in range(1, MONTHS_PER_YEAR + 1):
            month_offset = offset_year * MONTHS_PER_YEAR + (month - 1)
            calendar_year, calendar_month = _calendar_year_month(start_year, start_month, month_offset)
            growth_rate = (
                growth_rate_provider(month_offset) if growth_rate_provider is not None else default_monthly_rate
            )

            one_time_expense_this_month = one_time_expenses_by_month_offset.get(month_offset, Money.zero())
            one_time_expense_annual = one_time_expense_annual + one_time_expense_this_month
            monthly_expense = monthly_recurring_expense + one_time_expense_this_month

            net_cashflow_month = monthly_net_income - monthly_expense
            discretionary_surplus_month = net_cashflow_month - _total(monthly_fixed_contributions)
            target_weights_this_month = (
                plan.allocation_policy.weights_for_age(age) if plan.allocation_policy is not None else {}
            )

            if discretionary_surplus_month.is_negative:
                withdrawal_outcome = withdraw_shortfall(
                    plan.accounts,
                    account_balances,
                    cost_basis_balances,
                    -discretionary_surplus_month,
                    plan.withdrawal_strategy,
                    portfolio_rules,
                    tax_rules.capital_gains,
                )
                contributions_this_month = _merge(monthly_fixed_contributions, _negate(withdrawal_outcome.withdrawals))
                unallocated_delta = -withdrawal_outcome.remaining_shortfall
                capital_gains_tax_month = withdrawal_outcome.capital_gains_tax
                cost_basis_balances = {
                    account_id: withdrawal_outcome.updated_cost_basis.get(account_id, Money.zero())
                    + monthly_fixed_contributions.get(account_id, Money.zero())
                    for account_id in account_balances
                }
            else:
                already_contributed_this_year = _merge(fixed_plan.contributions, discretionary_contributed_this_year)
                discretionary_contributions, unallocated_leftover = allocate_discretionary_surplus(
                    plan.accounts,
                    account_balances,
                    lifetime_contributions,
                    already_contributed_this_year,
                    discretionary_surplus_month,
                    plan.contribution_strategy,
                    portfolio_rules,
                    asset_class_by_account_id=asset_class_by_account_id,
                    target_weights=target_weights_this_month,
                )
                contributions_this_month = _merge(monthly_fixed_contributions, discretionary_contributions)
                unallocated_delta = unallocated_leftover
                capital_gains_tax_month = Money.zero()
                discretionary_contributed_this_year = _merge(
                    discretionary_contributed_this_year, discretionary_contributions
                )
                cost_basis_balances = {
                    account_id: cost_basis_balances.get(account_id, Money.zero())
                    + contributions_this_month.get(account_id, Money.zero())
                    for account_id in account_balances
                }

            account_balances = {
                account_id: _floor_zero(
                    _grow(balance, growth_rate) + contributions_this_month.get(account_id, Money.zero())
                )
                for account_id, balance in account_balances.items()
            }
            lifetime_contributions = {
                account_id: lifetime_contributions[account_id] + contributions_this_month.get(account_id, Money.zero())
                for account_id in lifetime_contributions
            }
            surplus_reserve = _grow(surplus_reserve, growth_rate) + unallocated_delta

            if target_weights_this_month:
                # 新規拠出(discretionary配分のドリフト考慮)で埋めきれなかった乖離を、
                # 過大な口座の売却→過小な口座への再投資で解消する（ギャップ分析3.7）。
                rebalance_outcome = rebalance(
                    plan,
                    account_balances,
                    cost_basis_balances,
                    lifetime_contributions,
                    asset_class_by_account_id,
                    target_weights_this_month,
                    portfolio_rules,
                    tax_rules.capital_gains,
                )
                account_balances = rebalance_outcome.account_balances
                cost_basis_balances = rebalance_outcome.cost_basis_balances
                lifetime_contributions = rebalance_outcome.lifetime_contributions
                capital_gains_tax_month = capital_gains_tax_month + rebalance_outcome.capital_gains_tax
                surplus_reserve = surplus_reserve + rebalance_outcome.unreinvested_proceeds

            capital_gains_tax_annual = capital_gains_tax_annual + capital_gains_tax_month

            balances_snapshot = {**account_balances, UNALLOCATED_SURPLUS_KEY: surplus_reserve}
            networth = sum(balances_snapshot.values(), Money.zero())

            monthly_projections.append(
                MonthlyProjection(
                    year=calendar_year,
                    month=calendar_month,
                    age_self=age,
                    gross_income=monthly_gross_income,
                    pension_income=monthly_pension_income,
                    net_income=monthly_net_income,
                    total_expense=monthly_expense,
                    net_cashflow=net_cashflow_month,
                    capital_gains_tax=capital_gains_tax_month,
                    account_balances=dict(balances_snapshot),
                    networth=networth,
                )
            )

        total_expense_including_one_time = total_expense_annual + one_time_expense_annual
        yearly_projections.append(
            YearlyProjection(
                year=year,
                age_self=age,
                gross_income=gross_income_annual,
                pension_income=pension_income_annual,
                income_tax=tax_result.income_tax,
                resident_tax=tax_result.resident_tax,
                social_insurance=tax_result.social_insurance,
                net_income=tax_result.net_income,
                total_expense=total_expense_including_one_time,
                net_cashflow=tax_result.net_income - total_expense_including_one_time,
                capital_gains_tax=capital_gains_tax_annual,
                account_balances=balances_snapshot,
                networth=networth,
            )
        )

    milestone_outcomes = evaluate_milestones(plan, yearly_projections)

    return SimulationResult(
        yearly_projections=yearly_projections,
        monthly_projections=monthly_projections,
        milestone_outcomes=milestone_outcomes,
    )


def _initial_balance(portfolio: Optional[Portfolio]) -> Money:
    if portfolio is None:
        return Money.zero()
    total = Money.zero()
    for holding in portfolio.holdings:
        total = total + holding.cost_basis
    return total


def _asset_class_by_account_id(portfolios: dict[str, Portfolio]) -> dict[str, AssetClass]:
    """口座ごとの資産クラスを解決する（現状のSheets入力モデルは1口座=1資産クラスの前提。
    複数保有がある場合は先頭のholdingを代表として扱う）。AllocationPolicyによる
    ドリフト考慮の拠出配分・月次リバランスで、口座がどの資産クラスに属するかを引くのに使う。
    """

    result: dict[str, AssetClass] = {}
    for account_id, portfolio in portfolios.items():
        if portfolio.holdings:
            result[account_id] = portfolio.holdings[0].asset.asset_class
    return result


def _divide_by_12(amount: Money) -> Money:
    return Money.of(amount.amount / MONTHS_PER_YEAR)


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


def _negate(amounts: dict[str, Money]) -> dict[str, Money]:
    return {account_id: -amount for account_id, amount in amounts.items()}


def _grow(money: Money, rate: Rate) -> Money:
    return money + rate.apply_to(money)


def _floor_zero(money: Money) -> Money:
    # マイナス成長率下での取り崩し等、稀な端数ケースで口座残高が僅かに負になるのを防ぐ安全弁。
    return money if not money.is_negative else Money.zero()


def _grown_amount(amount: Money, growth_rate: Rate, offset: int) -> Money:
    factor = (Decimal(1) + growth_rate.value) ** offset
    return amount * factor


def resolve_start_year(plan: Plan) -> int:
    condition = plan.start_condition
    if condition.condition_type == StartConditionType.FIXED_DATE:
        return condition.fixed_date.year
    return date.today().year


def resolve_start_month(plan: Plan) -> int:
    condition = plan.start_condition
    if condition.condition_type == StartConditionType.FIXED_DATE:
        return condition.fixed_date.month
    return date.today().month


def _calendar_year_month(start_year: int, start_month: int, month_offset: int) -> tuple[int, int]:
    """月次オフセット(0始まり)を実際の西暦年・月に変換する。

    YearlyProjection.yearは「プラン開始からN年目」という単純な連番（start_year+offset_year）の
    ままだが、MonthlyProjectionの年月はOneTimeExpense等の発生月と一致させる必要があるため、
    start_monthが1月以外（例: StartConditionType.TODAYで年の途中から始まるプラン）でも
    実際のカレンダー通りの年月になるようここで変換する。
    """

    total_months = (start_month - 1) + month_offset
    return start_year + total_months // MONTHS_PER_YEAR, total_months % MONTHS_PER_YEAR + 1


def _resolve_end_year(plan: Plan, start_year: int) -> int:
    retirement_year = _retirement_year(plan, start_year)
    if retirement_year is not None:
        life_expectancy_year = plan.user.birth_date.year + DEFAULT_LIFE_EXPECTANCY_AGE
        return max(retirement_year, life_expectancy_year, start_year)
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


def _education_expense_monthly_total(
    children: list[Child], bands: list[EducationExpenseBand], year: int
) -> Money:
    """その年に該当する子供の年齢に基づき、教育費バンド（小学校・塾等）の月額合計を返す
    （ギャップ分析3.2）。物価上昇は考慮しない（既存のinflation_rate同様、現時点では未対応）。
    """

    age_by_child_id = {child.child_id: year - child.birth_date.year for child in children}
    total = Money.zero()
    for band in bands:
        age = age_by_child_id.get(band.child_id)
        if age is not None and band.applies_to_age(age):
            total = total + band.monthly_amount
    return total


def _one_time_expenses_by_month_offset(
    one_time_expenses: list[OneTimeExpense], start_year: int, start_month: int, birth_date: date
) -> dict[int, Money]:
    """車・旅行・住宅購入等の単発支出（ギャップ分析3.3）を、発生する月次オフセットごとに
    集計する。同じ月に複数の単発支出が重なる場合は合算する。
    """

    result: dict[int, Money] = {}
    for expense in one_time_expenses:
        resolved = resolve_condition_month(expense.trigger, start_year, start_month, birth_date)
        if resolved is None:
            continue
        target_year, target_month = resolved
        target_offset = (target_year - start_year) * MONTHS_PER_YEAR + (target_month - start_month)
        result[target_offset] = result.get(target_offset, Money.zero()) + expense.amount
    return result
