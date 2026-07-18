from __future__ import annotations

from dataclasses import dataclass, replace

from core.domain.pension import PensionRules
from core.domain.plan import Plan
from core.domain.portfolio import Portfolio
from core.domain.portfolio_rules import PortfolioRules
from core.domain.tax_config import TaxRules
from core.domain.value_objects import Money, Rate
from core.simulation.projection.projection_engine import run_projection

DEFAULT_GROWTH_RATE_VARIATIONS: tuple[tuple[str, Rate], ...] = (
    ("-1%", Rate.from_percent(-1)),
    ("±0%", Rate.zero()),
    ("+1%", Rate.from_percent(1)),
)
DEFAULT_INFLATION_RATE_VARIATIONS: tuple[tuple[str, Rate], ...] = (
    ("-0.5%", Rate.from_percent(-0.5)),
    ("±0%", Rate.zero()),
    ("+0.5%", Rate.from_percent(0.5)),
)


@dataclass
class SensitivityResult:
    growth_rate_labels: list[str]
    inflation_rate_labels: list[str]
    final_networth_grid: dict[tuple[str, str], Money]  # (growth_label, inflation_label) -> 最終年ネットワース


def run_sensitivity_analysis(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
    pension_rules: PensionRules,
    growth_rate_variations: tuple[tuple[str, Rate], ...] = DEFAULT_GROWTH_RATE_VARIATIONS,
    inflation_rate_variations: tuple[tuple[str, Rate], ...] = DEFAULT_INFLATION_RATE_VARIATIONS,
) -> SensitivityResult:
    """assumptionsの成長率・インフレ率をplanの値からの増減幅で複数パターン振って再計算し、
    各組み合わせの最終年ネットワースをグリッドとして返すバッチ処理。

    既知の制約: inflation_rateは現時点のProjection Engineでは未使用（Income/Expenseが個別に
    growth_rateを持つ設計のため）。したがってinflation_rate側の軸を振っても結果は変わらない。
    growth_rate側は投資成長率として実際にrun_projection()へ反映される。
    """

    growth_rate_labels = [label for label, _delta in growth_rate_variations]
    inflation_rate_labels = [label for label, _delta in inflation_rate_variations]

    final_networth_grid: dict[tuple[str, str], Money] = {}
    for growth_label, growth_delta in growth_rate_variations:
        for inflation_label, inflation_delta in inflation_rate_variations:
            varied_plan = _apply_assumption_deltas(plan, growth_delta, inflation_delta)
            result = run_projection(varied_plan, portfolios, tax_rules, portfolio_rules, pension_rules)
            final_networth = result.yearly_projections[-1].networth if result.yearly_projections else Money.zero()
            final_networth_grid[(growth_label, inflation_label)] = final_networth

    return SensitivityResult(
        growth_rate_labels=growth_rate_labels,
        inflation_rate_labels=inflation_rate_labels,
        final_networth_grid=final_networth_grid,
    )


def _apply_assumption_deltas(plan: Plan, growth_delta: Rate, inflation_delta: Rate) -> Plan:
    assumptions = replace(
        plan.assumptions,
        investment_growth_rate=plan.assumptions.investment_growth_rate + growth_delta,
        inflation_rate=plan.assumptions.inflation_rate + inflation_delta,
    )
    return replace(plan, assumptions=assumptions)
