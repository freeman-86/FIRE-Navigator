from __future__ import annotations

from typing import Optional

from core.domain.simulation_result import SimulationResult

SCENARIO_COMPARISON_CHART_TYPE = "multi_line"


def build_scenario_comparison_chart(results_by_scenario_name: dict[str, SimulationResult]) -> dict:
    """複数シナリオのネットワース推移を、系列名=シナリオ名の折れ線グラフ用データとして生成する。

    シナリオごとに計算期間（例：退職年齢が異なればホライズンも異なる）が違うため、
    年をキーに値を引き当てる。値が存在しない年はNone（未算出）として扱う。
    v1.1システムアーキテクチャ設計書のOutput JSON charts形式に準拠する（type以外はnetworth_chartと同形）。
    """

    all_years: set[int] = set()
    for result in results_by_scenario_name.values():
        all_years.update(projection.year for projection in result.yearly_projections)
    x = sorted(all_years)

    series = []
    for scenario_name, result in results_by_scenario_name.items():
        networth_by_year = {projection.year: int(projection.networth.amount) for projection in result.yearly_projections}
        values: list[Optional[int]] = [networth_by_year.get(year) for year in x]
        series.append({"name": scenario_name, "values": values})

    return {"type": SCENARIO_COMPARISON_CHART_TYPE, "x": x, "series": series}
