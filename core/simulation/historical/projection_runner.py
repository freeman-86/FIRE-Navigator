from __future__ import annotations

from decimal import Decimal
from typing import Callable

from core.domain.asset import AssetClass
from core.domain.market_data import HistoricalDataset
from core.domain.pension import PensionRules
from core.domain.plan import Plan
from core.domain.portfolio import Portfolio
from core.domain.portfolio_rules import PortfolioRules
from core.domain.simulation_result import SimulationResult
from core.domain.tax_config import TaxRules
from core.simulation.historical.return_series_builder import build_return_series
from core.simulation.historical.scenario_builder import build_growth_rate_provider
from core.simulation.historical.window_generator import generate_windows
from core.simulation.projection.projection_engine import run_projection


def run_all_windows(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
    pension_rules: PensionRules,
    dataset: HistoricalDataset,
    weight_lookup: Callable[[int], dict[AssetClass, Decimal]],
    window_length: int,
) -> dict[int, SimulationResult]:
    """過去データセットの各「窓」（開始年をずらした実績リターン系列）についてProjection Engineを
    1回ずつ実行し、窓の開始年をキーにした結果を返す。
    """

    results: dict[int, SimulationResult] = {}
    for window_start_year in generate_windows(dataset, window_length):
        return_series = build_return_series(dataset, window_start_year, window_length)
        growth_rate_provider = build_growth_rate_provider(return_series, weight_lookup)
        results[window_start_year] = run_projection(
            plan, portfolios, tax_rules, portfolio_rules, pension_rules, growth_rate_provider=growth_rate_provider
        )
    return results
