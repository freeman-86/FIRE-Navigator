from __future__ import annotations

from core.domain.montecarlo_result import MonteCarloResult

PERCENTILE_BAND_CHART_TYPE = "percentile_band"


def build_percentile_band_chart(result: MonteCarloResult) -> dict:
    """MonteCarloResultの年次パーセンタイル分布(p10/p50/p90)を、v1.1 Output JSONの
    montecarlo_distribution_chart形式に準拠したグラフ用データとして生成する。
    """

    years = sorted(result.percentile_networth_by_year.keys())
    return {
        "type": PERCENTILE_BAND_CHART_TYPE,
        "x": years,
        "p10": [int(result.percentile_networth_by_year[year].p10.amount) for year in years],
        "p50": [int(result.percentile_networth_by_year[year].p50.amount) for year in years],
        "p90": [int(result.percentile_networth_by_year[year].p90.amount) for year in years],
    }
