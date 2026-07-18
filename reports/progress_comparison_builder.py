from __future__ import annotations

from typing import Optional

from core.domain.progress_record import ProgressRecord
from core.domain.simulation_result import SimulationResult

PROGRESS_COMPARISON_CHART_TYPE = "multi_line"
PLANNED_SERIES_NAME = "計画"
ACTUAL_SERIES_NAME = "実績"


def build_progress_comparison_chart(planned: SimulationResult, actual_records: list[ProgressRecord]) -> dict:
    """計画線（deterministic projectionのnetworth推移）と実績線（入力された実績ネットワース）を
    年で整列した比較用グラフデータとして生成する。値が存在しない年はNone（未算出/未入力）とする。
    """

    planned_by_year = {projection.year: int(projection.networth.amount) for projection in planned.yearly_projections}
    actual_by_year = {record.year: int(record.actual_networth.amount) for record in actual_records}

    years = sorted(set(planned_by_year) | set(actual_by_year))
    planned_values: list[Optional[int]] = [planned_by_year.get(year) for year in years]
    actual_values: list[Optional[int]] = [actual_by_year.get(year) for year in years]

    return {
        "type": PROGRESS_COMPARISON_CHART_TYPE,
        "x": years,
        "series": [
            {"name": PLANNED_SERIES_NAME, "values": planned_values},
            {"name": ACTUAL_SERIES_NAME, "values": actual_values},
        ],
    }
