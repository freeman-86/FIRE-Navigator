from __future__ import annotations

from typing import Optional

from core.domain.simulation_result import MonthlyProjection
from core.domain.value_objects import Money
from core.services.pipeline_service import PipelineOutcome
from reports.chart_builder import build_networth_chart
from reports.montecarlo_report_builder import build_percentile_band_chart
from reports.sensitivity_analysis_builder import build_sensitivity_table

OUTPUT_SCHEMA_VERSION = 3

_MONTHLY_DETAIL_FIXED_COLUMNS = (
    ("year", "西暦年"),
    ("month", "月"),
    ("age", "年齢"),
    ("net_income", "手取り収入"),
    ("total_expense", "支出"),
    ("net_cashflow", "収支"),
    ("capital_gains_tax", "譲渡税"),
    ("shortfall", "取り崩し不足額"),
    ("networth", "純資産"),
)


def _monthly_detail_to_json(monthly_projections: list[MonthlyProjection]) -> Optional[dict]:
    """月次詳細（旧Sheets版の出力_月次詳細シートに相当）をJSON化する。

    列は固定列（西暦年・月・年齢・手取り収入・支出・収支・譲渡税・取り崩し不足額・純資産）に、
    資産クラスごとの取り崩し額の列を動的に追加する（withdrawals_by_asset_classのキー集合は
    projection_engine側で全月とも同じになるようゼロ埋めされているため、先頭月のキーをそのまま
    列として使える。sheets_output_adapter.write_monthly_detail_table()と同じ方針）。
    """

    if not monthly_projections:
        return None

    asset_classes = sorted(monthly_projections[0].withdrawals_by_asset_class)
    columns = [key for key, _ in _MONTHLY_DETAIL_FIXED_COLUMNS] + asset_classes
    column_labels = [label for _, label in _MONTHLY_DETAIL_FIXED_COLUMNS] + asset_classes

    rows = []
    for projection in monthly_projections:
        row = [
            projection.year,
            projection.month,
            projection.age_self,
            int(projection.net_income.amount),
            int(projection.total_expense.amount),
            int(projection.net_cashflow.amount),
            int(projection.capital_gains_tax.amount),
            int(projection.remaining_shortfall.amount),
            int(projection.networth.amount),
        ]
        row += [
            int(projection.withdrawals_by_asset_class.get(asset_class, Money.zero()).amount)
            for asset_class in asset_classes
        ]
        rows.append(row)

    return {"columns": columns, "column_labels": column_labels, "shortfall_column_index": 7, "rows": rows}


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

    simulation_result/montecarlo_result（年次・試行ごとの生データを持つdataclass）自体は
    そのままではJSONにシリアライズできず、KPIカード・3種のグラフ・感応度分析グリッドは
    charts/tables/dashboardに要約済みの値だけで完結するため、あえてこのJSONには含めない。
    月次詳細（tables.monthly_detail）だけは、旧Sheets版の出力_月次詳細シートに相当する
    表として明示的にJSON化して含める（_monthly_detail_to_json）。

    outcome.succeeded が False（意味的な入力矛盾で計算が中断した）場合は、dashboard/tables/charts
    はすべて空のままerrorsだけを埋めて返す。
    """

    dashboard = _dashboard_to_json(outcome.dashboard) if outcome.dashboard is not None else None
    sensitivity_table = build_sensitivity_table(outcome.sensitivity_result) if outcome.sensitivity_result else None
    monthly_detail = _monthly_detail_to_json(outcome.result.monthly_projections) if outcome.result is not None else None
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
            "monthly_detail": monthly_detail,
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
