from __future__ import annotations

from core.domain.montecarlo_result import MonteCarloResult, PercentileBand
from core.domain.simulation_result import SimulationResult
from core.domain.value_objects import Money
from core.simulation.montecarlo.success_judge import is_successful


def compute_statistics(trial_results: list[SimulationResult]) -> MonteCarloResult:
    """全試行の結果を集計し、成功確率・年次パーセンタイル分布(p10/p50/p90)を算出する。"""

    trials = len(trial_results)
    success_count = sum(1 for trial in trial_results if is_successful(trial))
    success_rate = success_count / trials if trials > 0 else 0.0

    years = sorted({projection.year for trial in trial_results for projection in trial.yearly_projections})
    percentile_networth_by_year: dict[int, PercentileBand] = {}
    for year in years:
        networths = sorted(
            projection.networth
            for trial in trial_results
            for projection in trial.yearly_projections
            if projection.year == year
        )
        percentile_networth_by_year[year] = PercentileBand(
            p10=_percentile(networths, 10),
            p50=_percentile(networths, 50),
            p90=_percentile(networths, 90),
        )

    return MonteCarloResult(
        trials=trials,
        success_count=success_count,
        success_rate=success_rate,
        percentile_networth_by_year=percentile_networth_by_year,
    )


def _percentile(sorted_values: list[Money], percentile: int) -> Money:
    if not sorted_values:
        return Money.zero()
    index = min(int(len(sorted_values) * percentile / 100), len(sorted_values) - 1)
    return sorted_values[index]
