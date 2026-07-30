from __future__ import annotations

from datetime import date

from core.domain.montecarlo_result import MonteCarloResult
from core.domain.plan import Plan
from core.domain.value_objects import AgeAt

PERCENTILE_BAND_CHART_TYPE = "percentile_band"


def build_percentile_band_chart(plan: Plan, result: MonteCarloResult) -> dict:
    """MonteCarloResultの年次パーセンタイル分布(p10/p50/p90)を、v1.1 Output JSONの
    montecarlo_distribution_chart形式に準拠したグラフ用データとして生成する。

    agesは表示用に年末時点（12/31）の年齢を添える近似値（決定論的Projection Engineの
    age_self、すなわち年内最後の月時点の年齢とおおむね一致するが、厳密な月次計算ではない）。
    """

    years = sorted(result.percentile_networth_by_year.keys())
    ages = [AgeAt(plan.user.birth_date, date(year, 12, 31)).years for year in years]
    return {
        "type": PERCENTILE_BAND_CHART_TYPE,
        "x": years,
        "ages": ages,
        "p10": [int(result.percentile_networth_by_year[year].p10.amount) for year in years],
        "p50": [int(result.percentile_networth_by_year[year].p50.amount) for year in years],
        "p90": [int(result.percentile_networth_by_year[year].p90.amount) for year in years],
    }
