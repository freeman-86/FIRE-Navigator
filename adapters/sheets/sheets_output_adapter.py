from __future__ import annotations

from typing import Optional

import gspread

from adapters.sheets.sheet_mapping import (
    CAPITAL_GAINS_TAX_HEADER,
    DASHBOARD_CURRENT_NETWORTH_LABEL,
    DASHBOARD_DEPLETION_AGE_LABEL,
    DASHBOARD_ENDING_NETWORTH_LABEL,
    DASHBOARD_EXTRA_ANNUAL_BUDGET_LABEL,
    DASHBOARD_EXTRA_MONTHLY_BUDGET_LABEL,
    DASHBOARD_NO_DEPLETION_TEXT,
    DASHBOARD_SURPLUS_LABEL,
    DASHBOARD_TARGET_NETWORTH_LABEL,
    AGE_HEADER,
    HISTORICAL_METHOD_LABEL,
    METHOD_HEADER,
    MONTECARLO_METHOD_LABEL,
    MONTH_HEADER,
    NET_CASHFLOW_HEADER,
    NET_INCOME_HEADER,
    NETWORTH_HEADER,
    OUTPUT_DASHBOARD_SHEET,
    OUTPUT_MONTECARLO_SHEET,
    OUTPUT_MONTHLY_DETAIL_SHEET,
    OUTPUT_NETWORTH_SHEET,
    OUTPUT_PROGRESS_COMPARISON_SHEET,
    OUTPUT_SCENARIO_COMPARISON_SHEET,
    OUTPUT_SENSITIVITY_ANALYSIS_SHEET,
    P10_HEADER,
    P50_HEADER,
    P90_HEADER,
    SENSITIVITY_TABLE_HEADER,
    TOTAL_EXPENSE_HEADER,
    YEAR_HEADER,
)
from adapters.sheets.sheets_number_format import money_column_format_requests, money_row_format_requests
from core.domain.montecarlo_result import MonteCarloResult
from core.domain.simulation_result import SimulationResult
from core.domain.value_objects import Money

BREAKDOWN_CHART_TITLE = "純資産推移（口座種別内訳）"
SCENARIO_COMPARISON_CHART_TITLE = "シナリオ比較（純資産推移）"
PROGRESS_COMPARISON_CHART_TITLE = "計画 vs 実績"
MONTECARLO_CHART_TITLE = "モンテカルロ・シミュレーション（p10/p50/p90）"
HISTORICAL_BACKTEST_CHART_TITLE = "ヒストリカル・バックテスト（p10/p50/p90）"


def write_networth_table(spreadsheet: gspread.Spreadsheet, simulation_result: SimulationResult, networth_chart: dict) -> None:
    """出力_純資産推移: 年次のネットワース・譲渡税に加え、口座種別ごとの内訳（積み上げエリアチャート用、
    旧・出力_純資産内訳）も同じシートにまとめて書き込む（タブ数削減のため統合）。

    networth_chartのx（年）はsimulation_result.yearly_projectionsと同じ順序・同じ長さで
    生成される（reports/chart_builder.py）ため、インデックスで対応付けられる。
    """

    breakdown_names = [series["name"] for series in networth_chart["series"]]
    header = [YEAR_HEADER, NETWORTH_HEADER, CAPITAL_GAINS_TAX_HEADER] + breakdown_names
    rows: list[list[object]] = [header]
    for index, projection in enumerate(simulation_result.yearly_projections):
        breakdown_values = [_cell_value(series["values"][index]) for series in networth_chart["series"]]
        rows.append(
            [projection.year, int(projection.networth.amount), int(projection.capital_gains_tax.amount)]
            + breakdown_values
        )

    worksheet = _get_or_create_worksheet(spreadsheet, OUTPUT_NETWORTH_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")
    _apply_money_column_format(spreadsheet, worksheet, rows)

    if breakdown_names:
        _replace_native_chart(
            spreadsheet,
            worksheet,
            title=BREAKDOWN_CHART_TITLE,
            chart_type="AREA",
            stacked_type="STACKED",
            num_rows=len(rows),
            num_series=len(breakdown_names),
            series_cols=list(range(3, 3 + len(breakdown_names))),
            anchor_col=len(header) + 2,
        )


def write_monthly_detail_table(spreadsheet: gspread.Spreadsheet, simulation_result: SimulationResult) -> None:
    """SimulationResult.monthly_projections（Sprint12 月次化）を、月次の資金の動きが一覧できる
    出力_月次詳細シートへ書き込む。「FIRE後、毎月いくら使えるか」を月単位で確認できるようにする。

    末尾に資産クラスごとの取り崩し額（税引き前の売却額）の列を追加する。列は入力_口座の
    資産クラス構成に応じて動的に増減する（withdrawals_by_asset_classのキー、projection_engine.py
    で全月とも同じ資産クラス集合になるようゼロ埋めされているため、先頭月のキー集合をそのまま
    列として使える）。
    """

    asset_classes = sorted(simulation_result.monthly_projections[0].withdrawals_by_asset_class) \
        if simulation_result.monthly_projections else []

    rows: list[list[object]] = [
        [YEAR_HEADER, MONTH_HEADER, AGE_HEADER, NET_INCOME_HEADER, TOTAL_EXPENSE_HEADER, NET_CASHFLOW_HEADER,
         CAPITAL_GAINS_TAX_HEADER, NETWORTH_HEADER] + asset_classes
    ]
    rows += [
        [
            projection.year,
            projection.month,
            projection.age_self,
            int(projection.net_income.amount),
            int(projection.total_expense.amount),
            int(projection.net_cashflow.amount),
            int(projection.capital_gains_tax.amount),
            int(projection.networth.amount),
        ]
        + [int(projection.withdrawals_by_asset_class.get(asset_class, Money.zero()).amount) for asset_class in asset_classes]
        for projection in simulation_result.monthly_projections
    ]
    worksheet = _get_or_create_worksheet(spreadsheet, OUTPUT_MONTHLY_DETAIL_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")
    _apply_money_column_format(spreadsheet, worksheet, rows)


def write_dashboard(spreadsheet: gspread.Spreadsheet, dashboard: dict) -> None:
    """reports.dashboard_builder.build_dashboard()の出力を、旧ドラフトのDashboardシートを踏襲した
    縦持ちの1画面要約ビュー（出力_ダッシュボード）として書き込む。
    """

    depletion_age = dashboard["depletion_age"]
    rows: list[list[object]] = [
        [DASHBOARD_CURRENT_NETWORTH_LABEL, int(dashboard["current_networth"].amount)],
        [DASHBOARD_EXTRA_ANNUAL_BUDGET_LABEL, int(dashboard["extra_annual_budget"].amount)],
        [DASHBOARD_EXTRA_MONTHLY_BUDGET_LABEL, int(dashboard["extra_monthly_budget"].amount)],
        [DASHBOARD_DEPLETION_AGE_LABEL, depletion_age if depletion_age is not None else DASHBOARD_NO_DEPLETION_TEXT],
        [DASHBOARD_TARGET_NETWORTH_LABEL, int(dashboard["target_ending_networth"].amount)],
        [DASHBOARD_ENDING_NETWORTH_LABEL, int(dashboard["ending_networth"].amount)],
        [DASHBOARD_SURPLUS_LABEL, int(dashboard["surplus_vs_target"].amount)],
    ]

    worksheet = _get_or_create_worksheet(spreadsheet, OUTPUT_DASHBOARD_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")
    _apply_money_row_format(spreadsheet, worksheet, rows)


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


def write_montecarlo_and_historical_result(
    spreadsheet: gspread.Spreadsheet,
    montecarlo: Optional[tuple[MonteCarloResult, dict]] = None,
    historical: Optional[tuple[MonteCarloResult, dict]] = None,
) -> None:
    """モンテカルロ・ヒストリカルバックテストの結果（成功確率＋年次パーセンタイル分布）を、
    「手法」列で区別しつつ1枚の出力_モンテカルロシートへまとめて書き込む
    （タブ数削減のため旧・出力_ヒストリカルバックテストは統合により廃止）。

    montecarlo/historicalはそれぞれ(MonteCarloResult, percentile_chart)のタプルで渡し、
    省略（None）された方は書かない（--skip-montecarlo/--skip-historical実行時に対応）。
    手法ごとに専用のヘッダー行付きブロックとして縦に積み上げる（チャートのデータ範囲・
    成功確率の要約行を手法ごとに独立させるため）。両方Noneの場合は何もしない。
    """

    header = [METHOD_HEADER, YEAR_HEADER, P10_HEADER, P50_HEADER, P90_HEADER]
    rows: list[list[object]] = []
    blocks: list[tuple[str, MonteCarloResult, int, int]] = []  # (手法, result, ブロック開始行, 終了行) 0始まり

    for method_label, entry in (
        (MONTECARLO_METHOD_LABEL, montecarlo),
        (HISTORICAL_METHOD_LABEL, historical),
    ):
        if entry is None:
            continue
        result, percentile_chart = entry
        block_start = len(rows)
        rows.append(header)
        for index, year in enumerate(percentile_chart["x"]):
            rows.append(
                [method_label, year, percentile_chart["p10"][index], percentile_chart["p50"][index], percentile_chart["p90"][index]]
            )
        blocks.append((method_label, result, block_start, len(rows)))

    if not rows:
        return

    worksheet = _get_or_create_worksheet(spreadsheet, OUTPUT_MONTECARLO_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")
    _apply_money_column_format(spreadsheet, worksheet, rows)

    summary_lines = [
        [f"{method_label} 成功確率: {result.success_rate:.1%}（{result.success_count}/{result.trials}試行）"]
        for method_label, result, _, _ in blocks
    ]
    summary_start_row = len(rows) + 2  # 1始まりのシート行番号（データの後に空行を1つ挟む）
    required_rows = summary_start_row + len(summary_lines) - 1
    if worksheet.row_count < required_rows:
        worksheet.resize(rows=required_rows)
    worksheet.update(values=summary_lines, range_name=f"A{summary_start_row}")

    chart_titles = {MONTECARLO_METHOD_LABEL: MONTECARLO_CHART_TITLE, HISTORICAL_METHOD_LABEL: HISTORICAL_BACKTEST_CHART_TITLE}
    anchor_col = len(header) + 2
    for chart_index, (method_label, _, block_start, block_end) in enumerate(blocks):
        _replace_native_chart(
            spreadsheet,
            worksheet,
            title=chart_titles[method_label],
            chart_type="LINE",
            stacked_type=None,
            num_rows=block_end - block_start,
            num_series=3,
            row_start=block_start,
            domain_col=1,
            series_cols=[2, 3, 4],
            anchor_row=chart_index * 20,
            anchor_col=anchor_col,
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
    _apply_money_column_format(spreadsheet, worksheet, rows)
    return worksheet


def _cell_value(value: object) -> object:
    return "" if value is None else value


def _apply_money_column_format(spreadsheet: gspread.Spreadsheet, worksheet: gspread.Worksheet, rows: list[list[object]]) -> None:
    """ヘッダー行付きテーブルの金額列にカンマ区切りの表示形式を設定する（1行目をヘッダーとみなす）。"""

    if not rows:
        return
    header = [str(h) for h in rows[0]]
    requests = money_column_format_requests(worksheet.id, header, 1, len(rows))
    if requests:
        spreadsheet.batch_update({"requests": requests})


def _apply_money_row_format(spreadsheet: gspread.Spreadsheet, worksheet: gspread.Worksheet, rows: list[list[object]]) -> None:
    """縦持ち(A列=ラベル/B列=値)シートの金額行にカンマ区切りの表示形式を設定する。"""

    row_labels = [str(row[0]) if row else "" for row in rows]
    requests = money_row_format_requests(worksheet.id, row_labels)
    if requests:
        spreadsheet.batch_update({"requests": requests})


CLEAR_FORMAT_ROW_COUNT = 500
CLEAR_FORMAT_COL_COUNT = 30


def _get_or_create_worksheet(
    spreadsheet: gspread.Spreadsheet, sheet_name: str, rows: list[list[object]]
) -> gspread.Worksheet:
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
        # worksheet.clear()は値のみを消し、書式（数値の表示形式等）は残る。列構成が実行のたびに
        # 変わりうる出力シート（純資産推移の内訳列、モンテカルロ等）では、以前の実行で別の列に
        # 付けたカンマ区切り表示形式が新しい列構成に残存してしまう（例: 列がずれて年の列に
        # カンマ書式が残る）ため、書き込み前に明示的に表示形式をクリアする。
        spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": worksheet.id,
                                "startRowIndex": 0,
                                "endRowIndex": CLEAR_FORMAT_ROW_COUNT,
                                "startColumnIndex": 0,
                                "endColumnIndex": CLEAR_FORMAT_COL_COUNT,
                            },
                            "cell": {"userEnteredFormat": {"numberFormat": None}},
                            "fields": "userEnteredFormat.numberFormat",
                        }
                    }
                ]
            }
        )
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
    row_start: int = 0,
    domain_col: int = 0,
    series_cols: Optional[list[int]] = None,
    anchor_row: int = 0,
    anchor_col: Optional[int] = None,
) -> None:
    """num_rows/num_seriesはヘッダー行込みの行数・系列数の基本形（domain=列0、系列=列1..num_series、
    アンカーは表の右側）。1枚のシートに複数の表・チャートを配置する場合（純資産推移の内訳、
    モンテカルロ/ヒストリカルの統合等）は、row_start/domain_col/series_cols/anchor_row/anchor_colで
    データ範囲・アンカー位置を明示的に指定する。
    """

    sheet_id = worksheet.id
    series_cols = series_cols if series_cols is not None else list(range(1, num_series + 1))
    anchor_col = anchor_col if anchor_col is not None else num_series + 2
    row_end = row_start + num_rows

    # チャートのアンカーセルがグリッド範囲外だとAPIエラーになるため、データ列より右側に余白を確保する。
    required_cols = anchor_col + 10
    if worksheet.col_count < required_cols:
        worksheet.resize(cols=required_cols)

    for chart_id in _existing_chart_ids(spreadsheet, sheet_id, title):
        spreadsheet.batch_update({"requests": [{"deleteEmbeddedObject": {"objectId": chart_id}}]})

    def _column_range(col: int) -> dict:
        return {
            "sources": [
                {
                    "sheetId": sheet_id,
                    "startRowIndex": row_start,
                    "endRowIndex": row_end,
                    "startColumnIndex": col,
                    "endColumnIndex": col + 1,
                }
            ]
        }

    series_requests = [
        {
            "series": {"sourceRange": _column_range(col)},
            "targetAxis": "LEFT_AXIS",
        }
        for col in series_cols
    ]

    basic_chart: dict[str, object] = {
        "chartType": chart_type,
        "legendPosition": "BOTTOM_LEGEND",
        "axis": [
            {"position": "BOTTOM_AXIS", "title": "年"},
            {"position": "LEFT_AXIS", "title": "純資産(円)"},
        ],
        "domains": [{"domain": {"sourceRange": _column_range(domain_col)}}],
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
                                    "rowIndex": anchor_row,
                                    "columnIndex": anchor_col,
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
