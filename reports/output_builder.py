from __future__ import annotations

from core.domain.plan import Plan
from core.domain.simulation_result import SimulationResult
from reports.chart_builder import build_networth_chart

OUTPUT_SCHEMA_VERSION = 2


def build_output_json(plan: Plan, simulation_result: SimulationResult) -> dict:
    """v1.1採用ロードマップ⑤に基づき、Output JSONにcharts等の拡張フィールドを導入する。

    Sprint4時点ではchartsのみを実データで埋め、summary/metrics/tables/diagnostics
    はSprint5以降、実際に使うデータが揃ったタイミングで値を追加していく（空のまま導入）。
    simulation_result/montecarlo_result/warnings/errorsはv1.0のOutput JSONと同じ位置づけ。
    """

    return {
        "plan_id": plan.plan_id,
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "summary": {},
        "metrics": {},
        "tables": {},
        "charts": {
            "networth_chart": build_networth_chart(plan, simulation_result),
        },
        "diagnostics": {},
        "simulation_result": simulation_result,
        "montecarlo_result": None,
        "warnings": [],
        "errors": [],
    }
