from __future__ import annotations

from typing import Optional

import gspread

from adapters.sheets.sheet_mapping import (
    NETWORTH_HEADER,
    OUTPUT_HISTORICAL_BACKTEST_SHEET,
    OUTPUT_MONTECARLO_SHEET,
    OUTPUT_NETWORTH_BREAKDOWN_SHEET,
    OUTPUT_NETWORTH_SHEET,
    OUTPUT_PROGRESS_COMPARISON_SHEET,
    OUTPUT_SCENARIO_COMPARISON_SHEET,
    OUTPUT_SENSITIVITY_ANALYSIS_SHEET,
    P10_HEADER,
    P50_HEADER,
    P90_HEADER,
    SENSITIVITY_TABLE_HEADER,
    YEAR_HEADER,
)
from core.domain.montecarlo_result import MonteCarloResult
from core.domain.simulation_result import SimulationResult

BREAKDOWN_CHART_TITLE = "純資産推移（口座種別内訳）"
SCENARIO_COMPARISON_CHART_TITLE = "シナリオ比較（純資産推移）"
PROGRESS_COMPARISON_CHART_TITLE = "計画 vs 実績"
MONTECARLO_CHART_TITLE = "モンテカルロ・シミュレーション（p10/p50/p90）"
HISTORICAL_BACKTEST_CHART_TITLE = "ヒストリカル・バックテスト（p10/p50/p90）"


def write_networth_table(spreadsheet: gspread.Spreadsheet, simulation_result: SimulationResult) -> None:
    rows: list[list[object]] = [[YEAR_HEADER, NETWORTH_HEADER]]
    rows += [
        [projection.year, int(projection.networth.amount)]
        for projection in simulation_result.yearly_projections
    ]
    worksheet = _get_or_create_worksheet(spreadsheet, OUTPUT_NETWORTH_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")


def write_networth_breakdown_chart(spreadsheet: gspread.Spreadsheet, networth_chart: dict) -> None:
    """charts.networth_chart形式のデータをテーブルとして書き込み、
    口座種別で積み上げたエリアチャート（Googleスプレッドシートのネイティブグラフ機能）として可視化する。
    """

    worksheet = _write_chart_table(spreadsheet, OUTPUT_NETWORTH_BREAKDOWN_SHEET, networth_chart)
    _replace_native_chart(
        spreadsheet,
        worksheet,
        title=BREAKDOWN_CHART_TITLE,
        chart_type="AREA",
        stacked_type="STACKED",
        num_rows=len(networth_chart["x"]) + 1,
        num_series=len(networth_chart["series"]),
    )


def write_scenario_comparison(spreadsheet: gspread.Spreadsheet, comparison_chart: dict) -> None:
    """複数シナリオのネットワース推移を折れ線グラフ（シナリオごとに1系列）として可視化する。"""

    worksheet = _write_chart_table(spreadsheet, OUTPUT_SCENARIO_COMPARISON_SHEET, comparison_chart)
    _replace_native_chart(
        spreadsheet,
        worksheet,
        title=SCENARIO_COMPARISON_CHART_TITLE,
        chart_type="LINE",
        stacked_type=None,
        num_rows=len(comparison_chart["x"]) + 1,
        num_series=len(comparison_chart["series"]),
    )


def write_sensitivity_table(spreadsheet: gspread.Spreadsheet, table: dict) -> None:
    """成長率×インフレ率の最終年ネットワースをグリッド表として書き込み、
    色スケール（条件付き書式）で感応度をヒートマップとして可視化する。
    """

    header = [SENSITIVITY_TABLE_HEADER] + list(table["column_labels"])
    rows: list[list[object]] = [header]
    for row_label, cell_row in zip(table["row_labels"], table["cells"]):
        rows.append([row_label] + list(cell_row))

    worksheet = _get_or_create_worksheet(spreadsheet, OUTPUT_SENSITIVITY_ANALYSIS_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")

    _replace_heatmap_conditional_format(
        spreadsheet,
        worksheet,
        num_data_rows=len(table["row_labels"]),
        num_data_cols=len(table["column_labels"]),
    )


def write_progress_comparison(spreadsheet: gspread.Spreadsheet, comparison_chart: dict) -> None:
    """計画線と実績線を折れ線グラフ（2系列）として可視化する。"""

    worksheet = _write_chart_table(spreadsheet, OUTPUT_PROGRESS_COMPARISON_SHEET, comparison_chart)
    _replace_native_chart(
        spreadsheet,
        worksheet,
        title=PROGRESS_COMPARISON_CHART_TITLE,
        chart_type="LINE",
        stacked_type=None,
        num_rows=len(comparison_chart["x"]) + 1,
        num_series=len(comparison_chart["series"]),
    )


def write_montecarlo_result(spreadsheet: gspread.Spreadsheet, result: MonteCarloResult, percentile_chart: dict) -> None:
    """Monte Carlo Engineの結果（成功確率＋年次パーセンタイル分布）を出力_モンテカルロシートへ書き込む。"""

    _write_percentile_result(spreadsheet, OUTPUT_MONTECARLO_SHEET, MONTECARLO_CHART_TITLE, result, percentile_chart)


def write_historical_backtest_result(
    spreadsheet: gspread.Spreadsheet, result: MonteCarloResult, percentile_chart: dict
) -> None:
    """Historical Engineの結果（成功確率＋窓ごとの年次パーセンタイル分布）を出力_ヒストリカルバックテストシートへ書き込む。"""

    _write_percentile_result(
        spreadsheet, OUTPUT_HISTORICAL_BACKTEST_SHEET, HISTORICAL_BACKTEST_CHART_TITLE, result, percentile_chart
    )


def _write_percentile_result(
    spreadsheet: gspread.Spreadsheet,
    sheet_name: str,
    chart_title: str,
    result: MonteCarloResult,
    percentile_chart: dict,
) -> None:
    header = [YEAR_HEADER, P10_HEADER, P50_HEADER, P90_HEADER]
    rows: list[list[object]] = [header]
    for index, year in enumerate(percentile_chart["x"]):
        rows.append(
            [year, percentile_chart["p10"][index], percentile_chart["p50"][index], percentile_chart["p90"][index]]
        )

    worksheet = _get_or_create_worksheet(spreadsheet, sheet_name, rows)
    worksheet.update(values=rows, range_name="A1")
    summary = f"成功確率: {result.success_rate:.1%}（{result.success_count}/{result.trials}試行）"
    summary_row = len(rows) + 2
    if worksheet.row_count < summary_row:
        worksheet.resize(rows=summary_row)
    worksheet.update(values=[[summary]], range_name=f"A{summary_row}")

    _replace_native_chart(
        spreadsheet,
        worksheet,
        title=chart_title,
        chart_type="LINE",
        stacked_type=None,
        num_rows=len(rows),
        num_series=3,
    )


def _write_chart_table(spreadsheet: gspread.Spreadsheet, sheet_name: str, chart: dict) -> gspread.Worksheet:
    header = [YEAR_HEADER] + [series["name"] for series in chart["series"]]
    rows: list[list[object]] = [header]
    for row_index, year in enumerate(chart["x"]):
        rows.append(
            [year] + [_cell_value(series["values"][row_index]) for series in chart["series"]]
        )

    worksheet = _get_or_create_worksheet(spreadsheet, sheet_name, rows)
    worksheet.update(values=rows, range_name="A1")
    return worksheet


def _cell_value(value: object) -> object:
    return "" if value is None else value


def _get_or_create_worksheet(
    spreadsheet: gspread.Spreadsheet, sheet_name: str, rows: list[list[object]]
) -> gspread.Worksheet:
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        cols = max(len(rows[0]), 2) if rows else 2
        return spreadsheet.add_worksheet(title=sheet_name, rows=max(len(rows), 10), cols=cols)


def _replace_native_chart(
    spreadsheet: gspread.Spreadsheet,
    worksheet: gspread.Worksheet,
    title: str,
    chart_type: str,
    stacked_type: Optional[str],
    num_rows: int,
    num_series: int,
) -> None:
    sheet_id = worksheet.id

    # チャートのアンカーセルがグリッド範囲外だとAPIエラーになるため、データ列より右側に余白を確保する。
    required_cols = num_series + 10
    if worksheet.col_count < required_cols:
        worksheet.resize(cols=required_cols)

    for chart_id in _existing_chart_ids(spreadsheet, sheet_id, title):
        spreadsheet.batch_update({"requests": [{"deleteEmbeddedObject": {"objectId": chart_id}}]})

    def _column_range(start_col: int, end_col: int) -> dict:
        return {
            "sources": [
                {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": num_rows,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col,
                }
            ]
        }

    series_requests = [
        {
            "series": {"sourceRange": _column_range(col, col + 1)},
            "targetAxis": "LEFT_AXIS",
        }
        for col in range(1, num_series + 1)
    ]

    basic_chart: dict[str, object] = {
        "chartType": chart_type,
        "legendPosition": "BOTTOM_LEGEND",
        "axis": [
            {"position": "BOTTOM_AXIS", "title": "年"},
            {"position": "LEFT_AXIS", "title": "純資産(円)"},
        ],
        "domains": [{"domain": {"sourceRange": _column_range(0, 1)}}],
        "series": series_requests,
        "headerCount": 1,
    }
    if stacked_type is not None:
        basic_chart["stackedType"] = stacked_type

    add_chart_request = {
        "requests": [
            {
                "addChart": {
                    "chart": {
                        "spec": {
                            "title": title,
                            "basicChart": basic_chart,
                        },
                        "position": {
                            "overlayPosition": {
                                "anchorCell": {
                                    "sheetId": sheet_id,
                                    "rowIndex": 0,
                                    "columnIndex": num_series + 2,
                                }
                            }
                        },
                    }
                }
            }
        ]
    }
    spreadsheet.batch_update(add_chart_request)


def _existing_chart_ids(spreadsheet: gspread.Spreadsheet, sheet_id: int, title: str) -> list[int]:
    metadata = spreadsheet.fetch_sheet_metadata()
    chart_ids = []
    for sheet in metadata.get("sheets", []):
        if sheet["properties"]["sheetId"] != sheet_id:
            continue
        for chart in sheet.get("charts", []):
            if chart.get("spec", {}).get("title") == title:
                chart_ids.append(chart["chartId"])
    return chart_ids


def _replace_heatmap_conditional_format(
    spreadsheet: gspread.Spreadsheet,
    worksheet: gspread.Worksheet,
    num_data_rows: int,
    num_data_cols: int,
) -> None:
    sheet_id = worksheet.id

    metadata = spreadsheet.fetch_sheet_metadata()
    existing_rule_count = 0
    for sheet in metadata.get("sheets", []):
        if sheet["properties"]["sheetId"] == sheet_id:
            existing_rule_count = len(sheet.get("conditionalFormats", []))
            break

    # 削除するたびにindexが詰まるため、常にindex=0を指定すればよい。
    requests = [{"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}} for _ in range(existing_rule_count)]

    requests.append(
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [
                        {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1 + num_data_rows,
                            "startColumnIndex": 1,
                            "endColumnIndex": 1 + num_data_cols,
                        }
                    ],
                    "gradientRule": {
                        "minpoint": {"color": {"red": 0.96, "green": 0.6, "blue": 0.6}, "type": "MIN"},
                        "midpoint": {
                            "color": {"red": 1.0, "green": 1.0, "blue": 0.8},
                            "type": "PERCENTILE",
                            "value": "50",
                        },
                        "maxpoint": {"color": {"red": 0.6, "green": 0.85, "blue": 0.6}, "type": "MAX"},
                    },
                },
                "index": 0,
            }
        }
    )

    spreadsheet.batch_update({"requests": requests})
