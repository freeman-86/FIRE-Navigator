from __future__ import annotations

from core.domain.market_data import HistoricalDataset
from core.domain.montecarlo_result import MonteCarloResult
from core.domain.pension import PensionRules
from core.domain.plan import Plan
from core.domain.portfolio import Portfolio
from core.domain.portfolio_rules import PortfolioRules
from core.domain.simulation_result import SimulationResult
from core.domain.tax_config import TaxRules
from core.simulation.historical.projection_runner import run_all_windows
from core.simulation.montecarlo.montecarlo_engine import build_weight_lookup
from core.simulation.montecarlo.statistics import compute_statistics
from core.simulation.projection.projection_engine import DEFAULT_PROJECTION_YEARS


def run_historical_backtest(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
    pension_rules: PensionRules,
    dataset: HistoricalDataset,
    window_length: int = DEFAULT_PROJECTION_YEARS,
) -> tuple[MonteCarloResult, dict[int, SimulationResult]]:
    """過去データセットから開始年をずらした複数の窓それぞれについて、実際に起きたリターン系列で
    Projection Engineを実行する（バックテスト）。統計処理はMonte Carlo Engineと共通の骨格
    （Projection Engineを繰り返し実行し統計をとる）を持つため、core.simulation.montecarlo.statistics
    を再利用する（設計書v1.1 ⑦の末尾で示唆される共通化を、shared/モジュールを新設せず関数レベルで
    先取りする）。

    戻り値は (集計結果, 窓の開始年→個別結果) のタプル。個別結果は窓ごとの推移を確認する用途に使う。
    """

    weight_lookup = build_weight_lookup(plan, portfolios)
    results_by_window = run_all_windows(
        plan, portfolios, tax_rules, portfolio_rules, pension_rules, dataset, weight_lookup, window_length
    )
    statistics = compute_statistics(list(results_by_window.values()))
    return statistics, results_by_window
