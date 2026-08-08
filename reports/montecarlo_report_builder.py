from __future__ import annotations

from datetime import date

from core.domain.montecarlo_result import MonteCarloResult
from core.domain.plan import Plan
from core.domain.value_objects import AgeAt

PERCENTILE_BAND_CHART_TYPE = "percentile_band"


def build_percentile_band_chart(plan: Plan, result: MonteCarloResult) -> dict:
    """MonteCarloResultの年次パーセンタイル分布(p5/p10/p20/p30/p50/p70/p80/p90/p95)を、v1.1 Output JSONの
    montecarlo_distribution_chart形式に準拠したグラフ用データとして生成する。

    agesは表示用の近似値。決定論的Projection Engineのage_self（core/simulation/projection/
    projection_engine.pyのage_at()）は、年内最後の月の「1日時点」での年齢を使う
    （例えば12/26生まれなら12/1時点ではまだ誕生日前なので、12/31基準より1歳若く出る）。
    Monte Carlo/Historical Engineは月次の年齢を持たないため、他の表（純資産推移・月次詳細）と
    表示上の年齢がずれないよう、age_at()と同じ「12/1時点」を基準に計算する。
    """

    years = sorted(result.percentile_networth_by_year.keys())
    birth_date = plan.user.birth_date
    ages = [
        0 if date(year, 12, 1) < birth_date else AgeAt(birth_date, date(year, 12, 1)).years for year in years
    ]
    return {
        "type": PERCENTILE_BAND_CHART_TYPE,
        "x": years,
        "ages": ages,
        "p5": [int(result.percentile_networth_by_year[year].p5.amount) for year in years],
        "p10": [int(result.percentile_networth_by_year[year].p10.amount) for year in years],
        "p20": [int(result.percentile_networth_by_year[year].p20.amount) for year in years],
        "p30": [int(result.percentile_networth_by_year[year].p30.amount) for year in years],
        "p50": [int(result.percentile_networth_by_year[year].p50.amount) for year in years],
        "p70": [int(result.percentile_networth_by_year[year].p70.amount) for year in years],
        "p80": [int(result.percentile_networth_by_year[year].p80.amount) for year in years],
        "p90": [int(result.percentile_networth_by_year[year].p90.amount) for year in years],
        "p95": [int(result.percentile_networth_by_year[year].p95.amount) for year in years],
    }
