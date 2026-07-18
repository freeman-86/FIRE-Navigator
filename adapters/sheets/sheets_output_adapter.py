from __future__ import annotations

import gspread

from adapters.sheets.sheet_mapping import OUTPUT_NETWORTH_BREAKDOWN_SHEET, OUTPUT_NETWORTH_SHEET
from core.domain.simulation_result import SimulationResult

BREAKDOWN_CHART_TITLE = "ネットワース推移（口座種別内訳）"


def write_networth_table(spreadsheet: gspread.Spreadsheet, simulation_result: SimulationResult) -> None:
    rows: list[list[object]] = [["year", "networth"]]
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

    header = ["year"] + [series["name"] for series in networth_chart["series"]]
    rows: list[list[object]] = [header]
    for row_index, year in enumerate(networth_chart["x"]):
        rows.append([year] + [series["values"][row_index] for series in networth_chart["series"]])

    worksheet = _get_or_create_worksheet(spreadsheet, OUTPUT_NETWORTH_BREAKDOWN_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")

    _replace_stacked_area_chart(
        spreadsheet,
        worksheet,
        num_rows=len(rows),
        num_series=len(networth_chart["series"]),
    )


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


def _replace_stacked_area_chart(
    spreadsheet: gspread.Spreadsheet,
    worksheet: gspread.Worksheet,
    num_rows: int,
    num_series: int,
) -> None:
    sheet_id = worksheet.id

    # チャートのアンカーセルがグリッド範囲外だとAPIエラーになるため、データ列より右側に余白を確保する。
    required_cols = num_series + 10
    if worksheet.col_count < required_cols:
        worksheet.resize(cols=required_cols)

    for chart_id in _existing_chart_ids(spreadsheet, sheet_id, BREAKDOWN_CHART_TITLE):
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

    add_chart_request = {
        "requests": [
            {
                "addChart": {
                    "chart": {
                        "spec": {
                            "title": BREAKDOWN_CHART_TITLE,
                            "basicChart": {
                                "chartType": "AREA",
                                "legendPosition": "BOTTOM_LEGEND",
                                "stackedType": "STACKED",
                                "axis": [
                                    {"position": "BOTTOM_AXIS", "title": "年"},
                                    {"position": "LEFT_AXIS", "title": "ネットワース(円)"},
                                ],
                                "domains": [{"domain": {"sourceRange": _column_range(0, 1)}}],
                                "series": series_requests,
                                "headerCount": 1,
                            },
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
