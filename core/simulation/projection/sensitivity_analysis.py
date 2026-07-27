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
    """各口座の期待リターン・インフレ率を複数パターン振って再計算し、各組み合わせの最終年
    ネットワースをグリッドとして返すバッチ処理。

    投資成長率という単一のプラン全体の仮定は持たないため（口座ごとの期待リターン(Asset.
    expected_return、入力_口座で必須)が実際の成長率として使われる）、growth_rate_variationsは
    全口座の期待リターンに一律で加える増減幅として適用する。

    既知の制約: inflation_rateはInput_収入・入力_支出で成長率が未入力の行の既定値として、
    スプレッドシート読込時（sheets_input_adapter._parse_growth_rate）にIncome/Expenseの
    growth_rateへ反映済みの値である。そのため、このplan（読込済みのPlan）のinflation_rateを
    ここで振っても、既にgrowth_rateが確定済みのIncome/Expenseには反映されず、inflation_rate側の
    軸を振っても結果は変わらない。growth_rate側は口座の期待リターンとして実際にrun_projection()へ
    反映される。
    """

    growth_rate_labels = [label for label, _delta in growth_rate_variations]
    inflation_rate_labels = [label for label, _delta in inflation_rate_variations]

    final_networth_grid: dict[tuple[str, str], Money] = {}
    for growth_label, growth_delta in growth_rate_variations:
        varied_portfolios = _apply_expected_return_delta(portfolios, growth_delta)
        for inflation_label, inflation_delta in inflation_rate_variations:
            varied_plan = _apply_inflation_delta(plan, inflation_delta)
            result = run_projection(varied_plan, varied_portfolios, tax_rules, portfolio_rules, pension_rules)
            final_networth = result.yearly_projections[-1].networth if result.yearly_projections else Money.zero()
            final_networth_grid[(growth_label, inflation_label)] = final_networth

    return SensitivityResult(
        growth_rate_labels=growth_rate_labels,
        inflation_rate_labels=inflation_rate_labels,
        final_networth_grid=final_networth_grid,
    )


def _apply_inflation_delta(plan: Plan, inflation_delta: Rate) -> Plan:
    assumptions = replace(plan.assumptions, inflation_rate=plan.assumptions.inflation_rate + inflation_delta)
    return replace(plan, assumptions=assumptions)


def _apply_expected_return_delta(portfolios: dict[str, Portfolio], growth_delta: Rate) -> dict[str, Portfolio]:
    """各口座の保有資産(Holding)の期待リターンに一律でgrowth_deltaを加えたportfoliosの複製を返す
    （元のportfoliosは変更しない）。"""

    return {
        account_id: replace(
            portfolio,
            holdings=[
                replace(holding, asset=replace(holding.asset, expected_return=holding.asset.expected_return + growth_delta))
                for holding in portfolio.holdings
            ],
        )
        for account_id, portfolio in portfolios.items()
    }
