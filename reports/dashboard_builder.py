from __future__ import annotations

import dataclasses
from typing import Optional

from core.domain.expense import Expense
from core.domain.pension import PensionRules
from core.domain.plan import Plan
from core.domain.portfolio import Portfolio
from core.domain.portfolio_rules import PortfolioRules
from core.domain.simulation_result import SimulationResult
from core.domain.tax_config import TaxRules
from core.domain.value_objects import Money, Rate
from core.simulation.projection.projection_engine import run_projection

REVERSE_CALC_EXPENSE_ID = "_reverse_calc_extra"
BISECTION_ITERATIONS = 30
BISECTION_UPPER_BOUND = Money.of(100_000_000)


def compute_asset_depletion_age(result: SimulationResult) -> Optional[int]:
    """資産(networth)が0以下になる最初の年齢を返す。枯渇しなければNone。"""

    for projection in result.yearly_projections:
        if projection.networth <= Money.zero():
            return projection.age_self
    return None


def _initial_networth(portfolios: dict[str, Portfolio]) -> Money:
    total = Money.zero()
    for portfolio in portfolios.values():
        for holding in portfolio.holdings:
            total = total + holding.cost_basis
    return total


def _ending_networth(result: SimulationResult) -> Money:
    if not result.yearly_projections:
        return Money.zero()
    return result.yearly_projections[-1].networth


def _run_with_extra_annual_expense(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
    pension_rules: PensionRules,
    extra_annual_expense: Money,
) -> SimulationResult:
    # 逆算の追加支出は物価変動を考慮しない一定額として扱う（旧ドラフト同様の簡略化）。
    extra_expense = Expense(
        expense_id=REVERSE_CALC_EXPENSE_ID,
        category="reverse_calc",
        amount=extra_annual_expense,
        growth_rate=Rate.zero(),
    )
    modified_plan = dataclasses.replace(plan, expenses=[*plan.expenses, extra_expense])
    return run_projection(modified_plan, portfolios, tax_rules, portfolio_rules, pension_rules)


def compute_reverse_annual_budget(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
    pension_rules: PensionRules,
    target_ending_networth: Money,
) -> Money:
    """シミュレーション最終年のnetworthがtarget_ending_networthを下回らない範囲で、
    年間いくら追加で使えるかを二分探索で求める。

    生活費を一律増額した仮想Planでrun_projectionを繰り返すだけで求められるため、
    core/simulation側の変更は不要（Reporting層の追加のみ）。
    """

    low = Money.zero()
    high = BISECTION_UPPER_BOUND

    baseline = _run_with_extra_annual_expense(plan, portfolios, tax_rules, portfolio_rules, pension_rules, low)
    if _ending_networth(baseline) < target_ending_networth:
        return Money.zero()

    at_high = _run_with_extra_annual_expense(plan, portfolios, tax_rules, portfolio_rules, pension_rules, high)
    if _ending_networth(at_high) >= target_ending_networth:
        return high

    for _ in range(BISECTION_ITERATIONS):
        mid = Money.of((low.amount + high.amount) / 2)
        result = _run_with_extra_annual_expense(plan, portfolios, tax_rules, portfolio_rules, pension_rules, mid)
        if _ending_networth(result) >= target_ending_networth:
            low = mid
        else:
            high = mid

    return low


def build_dashboard(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
    pension_rules: PensionRules,
    target_ending_networth: Money = Money.zero(),
) -> dict:
    """出力_ダッシュボード用のサマリを組み立てる（現在の純資産・逆算による追加可能額・
    資産枯渇年齢・目標資産との余裕）。
    """

    result = run_projection(plan, portfolios, tax_rules, portfolio_rules, pension_rules)
    ending_networth = _ending_networth(result)
    extra_annual_budget = compute_reverse_annual_budget(
        plan, portfolios, tax_rules, portfolio_rules, pension_rules, target_ending_networth
    )

    return {
        "current_networth": _initial_networth(portfolios),
        "extra_annual_budget": extra_annual_budget,
        "extra_monthly_budget": Money.of(extra_annual_budget.amount / 12),
        "depletion_age": compute_asset_depletion_age(result),
        "target_ending_networth": target_ending_networth,
        "ending_networth": ending_networth,
        "surplus_vs_target": ending_networth - target_ending_networth,
    }
