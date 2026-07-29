from __future__ import annotations

from core.services.pipeline_service import PipelineOutcome
from reports.chart_builder import build_networth_chart
from reports.montecarlo_report_builder import build_percentile_band_chart
from reports.sensitivity_analysis_builder import build_sensitivity_table

OUTPUT_SCHEMA_VERSION = 3


def _dashboard_to_json(dashboard: dict) -> dict:
    return {
        "current_networth": int(dashboard["current_networth"].amount),
        "extra_annual_budget": int(dashboard["extra_annual_budget"].amount),
        "extra_monthly_budget": int(dashboard["extra_monthly_budget"].amount),
        "depletion_age": dashboard["depletion_age"],
        "target_ending_networth": int(dashboard["target_ending_networth"].amount),
        "ending_networth": int(dashboard["ending_networth"].amount),
        "surplus_vs_target": int(dashboard["surplus_vs_target"].amount),
        "asset_allocation": [
            {
                "asset_class": entry["asset_class"],
                "amount": int(entry["amount"].amount),
                "weight": float(entry["weight"].value),
            }
            for entry in dashboard["asset_allocation"]
        ],
    }


def build_output_json(outcome: PipelineOutcome) -> dict:
    """PipelineOutcome（core.services.pipeline_service.run_pipeline_for_plan()の戻り値）を、
    Web UI・CLIのlocalモードの両方が使う単一のJSON出力（v1.1採用ロードマップ⑤のOutput JSON）へ
    まとめる。

    simulation_result/montecarlo_result（年次・月次・試行ごとの生データを持つdataclass）は
    そのままではJSONにシリアライズできず、現状のUI（KPIカード・3種のグラフ・感応度分析グリッド）は
    charts/tables/dashboardに要約済みの値だけで完結するため、あえてこのJSONには含めない
    （生データが必要な将来の機能はこことは別に用意する）。

    outcome.succeeded が False（意味的な入力矛盾で計算が中断した）場合は、dashboard/tables/charts
    はすべて空のままerrorsだけを埋めて返す。
    """

    dashboard = _dashboard_to_json(outcome.dashboard) if outcome.dashboard is not None else None
    sensitivity_table = build_sensitivity_table(outcome.sensitivity_result) if outcome.sensitivity_result else None
    networth_chart = build_networth_chart(outcome.plan, outcome.result) if outcome.result is not None else None
    montecarlo_chart = build_percentile_band_chart(outcome.montecarlo_result) if outcome.montecarlo_result else None
    historical_chart = build_percentile_band_chart(outcome.historical_result) if outcome.historical_result else None

    return {
        "plan_id": outcome.plan.plan_id,
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "dashboard": dashboard,
        "summary": {
            "montecarlo_success_rate": outcome.montecarlo_result.success_rate if outcome.montecarlo_result else None,
            "historical_success_rate": outcome.historical_result.success_rate if outcome.historical_result else None,
        },
        "metrics": {},
        "tables": {
            "sensitivity_table": sensitivity_table,
        },
        "charts": {
            "networth_chart": networth_chart,
            "montecarlo_distribution_chart": montecarlo_chart,
            "historical_distribution_chart": historical_chart,
        },
        "diagnostics": {
            "montecarlo_reference_1971_success_rate": (
                outcome.montecarlo_reference_1971_result.success_rate
                if outcome.montecarlo_reference_1971_result
                else None
            ),
            "timings": outcome.timings,
        },
        "warnings": [{"field_path": w.field_path, "message": w.message} for w in outcome.input_warnings],
        "errors": [{"field_path": e.field_path, "message": e.message} for e in outcome.semantic_errors],
    }
