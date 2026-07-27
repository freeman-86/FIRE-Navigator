from __future__ import annotations

from typing import Optional

import gspread

from adapters.sheets.sheet_mapping import (
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    CAPITAL_GAINS_TAX_HEADER,
    DASHBOARD_ALLOCATION_WEIGHT_HEADER,
    DASHBOARD_CURRENT_NETWORTH_LABEL,
    DASHBOARD_DEPLETION_AGE_LABEL,
    DASHBOARD_ENDING_NETWORTH_LABEL,
    DASHBOARD_EXTRA_ANNUAL_BUDGET_LABEL,
    DASHBOARD_EXTRA_MONTHLY_BUDGET_LABEL,
    DASHBOARD_HISTORICAL_SUCCESS_LABEL,
    DASHBOARD_MONTECARLO_REFERENCE_1971_LABEL,
    DASHBOARD_MONTECARLO_SUCCESS_LABEL,
    DASHBOARD_NO_DEPLETION_TEXT,
    DASHBOARD_SURPLUS_LABEL,
    DASHBOARD_TARGET_NETWORTH_LABEL,
    AGE_HEADER,
    HISTORICAL_METHOD_LABEL,
    METHOD_HEADER,
    MONTECARLO_METHOD_LABEL,
    MONTECARLO_REFERENCE_1971_NOTE,
    MONTH_HEADER,
    NET_CASHFLOW_HEADER,
    NET_INCOME_HEADER,
    NETWORTH_HEADER,
    OUTPUT_DASHBOARD_SHEET,
    OUTPUT_MONTECARLO_SHEET,
    OUTPUT_MONTHLY_DETAIL_SHEET,
    OUTPUT_NETWORTH_SHEET,
    OUTPUT_PROGRESS_COMPARISON_SHEET,
    OUTPUT_SENSITIVITY_ANALYSIS_SHEET,
    P10_HEADER,
    P50_HEADER,
    P90_HEADER,
    SENSITIVITY_TABLE_HEADER,
    SHORTFALL_HEADER,
    TOTAL_EXPENSE_HEADER,
    YEAR_HEADER,
)
from adapters.sheets.sheets_number_format import (
    money_column_format_requests,
    money_row_format_requests,
    percent_column_format_requests,
)
from core.domain.montecarlo_result import MonteCarloResult
from core.domain.simulation_result import SimulationResult
from core.domain.value_objects import Money

BREAKDOWN_CHART_TITLE = "純資産推移（口座種別内訳）"
PROGRESS_COMPARISON_CHART_TITLE = "計画 vs 実績"
MONTECARLO_CHART_TITLE = "モンテカルロ・シミュレーション（p10/p50/p90）"
HISTORICAL_BACKTEST_CHART_TITLE = "ヒストリカル・バックテスト（p10/p50/p90）"
DASHBOARD_NETWORTH_CHART_TITLE = "純資産推移"
MONTHLY_NETWORTH_CHART_TITLE = "純資産推移（月次）"

# 資産枯渇年齢・目標資産との余裕セルの条件付き書式（健全=緑／危険=赤）に使う背景色。
DASHBOARD_HEALTHY_CELL_COLOR = {"red": 0.72, "green": 0.88, "blue": 0.73}
DASHBOARD_DANGER_CELL_COLOR = {"red": 0.96, "green": 0.72, "blue": 0.71}
# 取り崩し不足額が発生した月（資産が足りていない月）を示す条件付き書式に使う背景色。
SHORTFALL_CELL_COLOR = {"red": 0.96, "green": 0.78, "blue": 0.78}
# Output_月次詳細で固定するヘッダー行数・左端の列数（年・月・年齢）。
MONTHLY_DETAIL_FROZEN_ROW_COUNT = 1
MONTHLY_DETAIL_FROZEN_COLUMN_COUNT = 3


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

    worksheet, requests = _get_or_create_worksheet(spreadsheet, OUTPUT_NETWORTH_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")
    requests += _money_column_format_requests(worksheet.id, rows)
    requests.append(_freeze_panes_request(worksheet.id, frozen_rows=1, frozen_columns=2))  # 西暦年・純資産

    if breakdown_names:
        sheet_state = _sheet_state(spreadsheet, worksheet.id)
        requests += _native_chart_requests(
            worksheet,
            sheet_state,
            title=BREAKDOWN_CHART_TITLE,
            chart_type="AREA",
            stacked_type="STACKED",
            num_rows=len(rows),
            num_series=len(breakdown_names),
            series_cols=list(range(3, 3 + len(breakdown_names))),
            anchor_col=len(header) + 2,
        )

    spreadsheet.batch_update({"requests": requests})


def write_monthly_detail_table(spreadsheet: gspread.Spreadsheet, simulation_result: SimulationResult) -> None:
    """SimulationResult.monthly_projections（Sprint12 月次化）を、月次の資金の動きが一覧できる
    出力_月次詳細シートへ書き込む。「FIRE後、毎月いくら使えるか」を月単位で確認できるようにする。

    末尾に資産クラスごとの取り崩し額（税引き前の売却額）の列を追加する。列は入力_口座の
    資産クラス構成に応じて動的に増減する（withdrawals_by_asset_classのキー、projection_engine.py
    で全月とも同じ資産クラス集合になるようゼロ埋めされているため、先頭月のキー集合をそのまま
    列として使える）。

    月数が多いシートでも見やすいよう、ヘッダー行と年・月・年齢の列を固定し、口座残高を取り崩しても
    なお賄いきれなかった月（取り崩し不足額列が0より大きい月＝本当に資産が足りていない月）を
    条件付き書式で強調し、純資産推移の簡易な折れ線グラフを埋め込む。収支自体のマイナスはFIRE後の
    取り崩し局面では正常な状態のため、収支のプラス/マイナスでは判定しない。
    """

    asset_classes = sorted(simulation_result.monthly_projections[0].withdrawals_by_asset_class) \
        if simulation_result.monthly_projections else []

    header = [YEAR_HEADER, MONTH_HEADER, AGE_HEADER, NET_INCOME_HEADER, TOTAL_EXPENSE_HEADER, NET_CASHFLOW_HEADER,
              CAPITAL_GAINS_TAX_HEADER, SHORTFALL_HEADER, NETWORTH_HEADER] + asset_classes
    rows: list[list[object]] = [header]
    rows += [
        [
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
        + [int(projection.withdrawals_by_asset_class.get(asset_class, Money.zero()).amount) for asset_class in asset_classes]
        for projection in simulation_result.monthly_projections
    ]
    worksheet, requests = _get_or_create_worksheet(spreadsheet, OUTPUT_MONTHLY_DETAIL_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")
    requests += _money_column_format_requests(worksheet.id, rows)
    requests.append(_freeze_panes_request(worksheet.id, MONTHLY_DETAIL_FROZEN_ROW_COUNT, MONTHLY_DETAIL_FROZEN_COLUMN_COUNT))

    # 条件付き書式・チャートの両方でシートの既存状態（conditionalFormats/charts）を参照するため、
    # fetch_sheet_metadata()は1回だけ呼んで使い回す（Google Sheets APIの読み取り回数を節約する）。
    sheet_state = _sheet_state(spreadsheet, worksheet.id)
    requests += _shortfall_conditional_format_requests(worksheet.id, sheet_state, header, len(rows))

    if len(rows) > 1:
        requests += _native_chart_requests(
            worksheet,
            sheet_state,
            title=MONTHLY_NETWORTH_CHART_TITLE,
            chart_type="LINE",
            stacked_type=None,
            num_rows=len(rows),
            num_series=1,
            domain_col=0,
            series_cols=[header.index(NETWORTH_HEADER)],
            anchor_col=len(header) + 2,
        )

    spreadsheet.batch_update({"requests": requests})


def write_dashboard(
    spreadsheet: gspread.Spreadsheet,
    dashboard: dict,
    simulation_result: Optional[SimulationResult] = None,
    montecarlo: Optional[MonteCarloResult] = None,
    historical: Optional[MonteCarloResult] = None,
    montecarlo_reference_1971: Optional[MonteCarloResult] = None,
) -> None:
    """reports.dashboard_builder.build_dashboard()の出力を、旧ドラフトのDashboardシートを踏襲した
    縦持ちの1画面要約ビュー（出力_ダッシュボード）として書き込む。

    A/B列のサマリ（既存7行 + モンテカルロ/ヒストリカルの成功確率）の下に、現在の資産配分の簡易表と
    純資産推移の折れ線グラフを積み上げる。simulation_result/montecarlo/historical/
    montecarlo_reference_1971は実行パイプライン上ダッシュボード本体の計算より後に出そろうため
    任意引数とし、省略時はその項目を書かない（呼び出し側の都合による省略であり、既存の7行サマリの
    構造・行位置は変えない）。

    montecarlo_reference_1971は、金本位制終了(1971年)以降のデータだけで分布・相関を推定し直した
    補足的な参考値（メインのモンテカルロ・ヒストリカルの計算・表示はそのまま、参考情報として1行
    追加するだけ）。
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
    depletion_age_row = 3
    surplus_row = 6

    if montecarlo is not None:
        rows.append([DASHBOARD_MONTECARLO_SUCCESS_LABEL, _success_rate_text(montecarlo)])
    if montecarlo_reference_1971 is not None:
        rows.append([DASHBOARD_MONTECARLO_REFERENCE_1971_LABEL, _success_rate_text(montecarlo_reference_1971)])
    if historical is not None:
        rows.append([DASHBOARD_HISTORICAL_SUCCESS_LABEL, _success_rate_text(historical)])

    allocation = dashboard.get("asset_allocation") or []
    allocation_header_row: Optional[int] = None
    if allocation:
        rows.append([])
        allocation_header_row = len(rows)
        rows.append([ASSET_CLASS_HEADER, BALANCE_HEADER, DASHBOARD_ALLOCATION_WEIGHT_HEADER])
        rows += [
            [entry["asset_class"], int(entry["amount"].amount), float(entry["weight"].value)] for entry in allocation
        ]

    networth_header_row: Optional[int] = None
    if simulation_result is not None and simulation_result.yearly_projections:
        rows.append([])
        networth_header_row = len(rows)
        rows.append([YEAR_HEADER, NETWORTH_HEADER])
        rows += [
            [projection.year, int(projection.networth.amount)] for projection in simulation_result.yearly_projections
        ]

    worksheet, requests = _get_or_create_worksheet(spreadsheet, OUTPUT_DASHBOARD_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")
    requests += _money_row_format_requests(worksheet.id, rows)

    sheet_state = _sheet_state(spreadsheet, worksheet.id)
    requests += _dashboard_conditional_format_requests(worksheet.id, sheet_state, depletion_age_row, surplus_row)
    # 縦持ち(A列=項目/B列=値)の要約に加え資産配分・純資産推移の表も積み上げるため、ヘッダー行という
    # 概念はないが、項目名が並ぶA列は他シートと一貫した操作性のため固定する。
    requests.append(_freeze_panes_request(worksheet.id, frozen_rows=0, frozen_columns=1))

    if allocation_header_row is not None:
        requests += percent_column_format_requests(
            worksheet.id,
            rows[allocation_header_row],
            allocation_header_row + 1,
            allocation_header_row + 1 + len(allocation),
        )

    if networth_header_row is not None:
        requests += _native_chart_requests(
            worksheet,
            sheet_state,
            title=DASHBOARD_NETWORTH_CHART_TITLE,
            chart_type="LINE",
            stacked_type=None,
            num_rows=len(simulation_result.yearly_projections) + 1,
            num_series=1,
            row_start=networth_header_row,
            domain_col=0,
            series_cols=[1],
            anchor_row=networth_header_row,
            anchor_col=3,
        )

    spreadsheet.batch_update({"requests": requests})


def _success_rate_text(result: MonteCarloResult) -> str:
    return f"{result.success_rate:.1%}（{result.success_count}/{result.trials}試行）"


def write_sensitivity_table(spreadsheet: gspread.Spreadsheet, table: dict) -> None:
    """成長率×インフレ率の最終年ネットワースをグリッド表として書き込み、
    色スケール（条件付き書式）で感応度をヒートマップとして可視化する。
    """

    header = [SENSITIVITY_TABLE_HEADER] + list(table["column_labels"])
    rows: list[list[object]] = [header]
    for row_label, cell_row in zip(table["row_labels"], table["cells"]):
        rows.append([row_label] + list(cell_row))

    worksheet, requests = _get_or_create_worksheet(spreadsheet, OUTPUT_SENSITIVITY_ANALYSIS_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")
    requests.append(_freeze_panes_request(worksheet.id, frozen_rows=1, frozen_columns=1))  # 投資成長率(行ラベル)

    sheet_state = _sheet_state(spreadsheet, worksheet.id)
    requests += _heatmap_conditional_format_requests(
        worksheet.id,
        sheet_state,
        num_data_rows=len(table["row_labels"]),
        num_data_cols=len(table["column_labels"]),
    )
    spreadsheet.batch_update({"requests": requests})


def write_progress_comparison(spreadsheet: gspread.Spreadsheet, comparison_chart: dict) -> None:
    """計画線と実績線を折れ線グラフ（2系列）として可視化する。"""

    worksheet, requests, header = _write_chart_table(spreadsheet, OUTPUT_PROGRESS_COMPARISON_SHEET, comparison_chart)
    sheet_state = _sheet_state(spreadsheet, worksheet.id)
    requests += _native_chart_requests(
        worksheet,
        sheet_state,
        title=PROGRESS_COMPARISON_CHART_TITLE,
        chart_type="LINE",
        stacked_type=None,
        num_rows=len(comparison_chart["x"]) + 1,
        num_series=len(comparison_chart["series"]),
    )
    spreadsheet.batch_update({"requests": requests})


def write_montecarlo_and_historical_result(
    spreadsheet: gspread.Spreadsheet,
    montecarlo: Optional[tuple[MonteCarloResult, dict]] = None,
    historical: Optional[tuple[MonteCarloResult, dict]] = None,
    montecarlo_reference_1971: Optional[MonteCarloResult] = None,
) -> None:
    """モンテカルロ・ヒストリカルバックテストの結果（成功確率＋年次パーセンタイル分布）を、
    「手法」列で区別しつつ1枚の出力_モンテカルロシートへまとめて書き込む
    （タブ数削減のため旧・出力_ヒストリカルバックテストは統合により廃止）。

    montecarlo/historicalはそれぞれ(MonteCarloResult, percentile_chart)のタプルで渡し、
    省略（None）された方は書かない（--skip-montecarlo/--skip-historical実行時に対応）。
    手法ごとに専用のヘッダー行付きブロックとして縦に積み上げる（チャートのデータ範囲・
    成功確率の要約行を手法ごとに独立させるため）。両方Noneの場合は何もしない。

    montecarlo_reference_1971は、金本位制終了(1971年)以降のデータだけで分布・相関を推定し直した
    補足的な参考値（出力_ダッシュボードと同様、専用の年次パーセンタイル表・チャートは作らず、
    メインのモンテカルロ成功確率の要約行のすぐ下に参考行を1行追加するだけ）。
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

    worksheet, requests = _get_or_create_worksheet(spreadsheet, OUTPUT_MONTECARLO_SHEET, rows)
    worksheet.update(values=rows, range_name="A1")
    requests += _money_column_format_requests(worksheet.id, rows)
    # 手法ブロックが縦に積み上がるため先頭ブロックのヘッダー行のみが対象になるが、
    # 手法・西暦年の列は他シートと一貫した操作性のため固定する。
    requests.append(_freeze_panes_request(worksheet.id, frozen_rows=1, frozen_columns=2))  # 手法・西暦年

    summary_lines: list[list[object]] = []
    for method_label, result, _, _ in blocks:
        summary_lines.append([f"{method_label} 成功確率: {_success_rate_text(result)}"])
        if method_label == MONTECARLO_METHOD_LABEL and montecarlo_reference_1971 is not None:
            summary_lines.append(
                [
                    f"{MONTECARLO_METHOD_LABEL} 成功確率{MONTECARLO_REFERENCE_1971_NOTE}: "
                    f"{_success_rate_text(montecarlo_reference_1971)}"
                ]
            )
    summary_start_row = len(rows) + 2  # 1始まりのシート行番号（データの後に空行を1つ挟む）
    required_rows = summary_start_row + len(summary_lines) - 1
    if worksheet.row_count < required_rows:
        requests.append(_resize_request(worksheet.id, rows=required_rows))

    # 行数を広げるリクエストは、その行へ値を書き込むworksheet.update()より先に確定させる必要が
    # あるため、ここで一度まとめて送る（以降のチャート関連リクエストは別バッチでよい）。
    spreadsheet.batch_update({"requests": requests})
    worksheet.update(values=summary_lines, range_name=f"A{summary_start_row}")

    chart_titles = {MONTECARLO_METHOD_LABEL: MONTECARLO_CHART_TITLE, HISTORICAL_METHOD_LABEL: HISTORICAL_BACKTEST_CHART_TITLE}
    anchor_col = len(header) + 2
    sheet_state = _sheet_state(spreadsheet, worksheet.id)
    chart_requests: list[dict] = []
    for chart_index, (method_label, _, block_start, block_end) in enumerate(blocks):
        chart_requests += _native_chart_requests(
            worksheet,
            sheet_state,
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
    spreadsheet.batch_update({"requests": chart_requests})


def _write_chart_table(
    spreadsheet: gspread.Spreadsheet, sheet_name: str, chart: dict
) -> tuple[gspread.Worksheet, list[dict], list[str]]:
    header = [YEAR_HEADER] + [series["name"] for series in chart["series"]]
    rows: list[list[object]] = [header]
    for row_index, year in enumerate(chart["x"]):
        rows.append(
            [year] + [_cell_value(series["values"][row_index]) for series in chart["series"]]
        )

    worksheet, requests = _get_or_create_worksheet(spreadsheet, sheet_name, rows)
    worksheet.update(values=rows, range_name="A1")
    requests += _money_column_format_requests(worksheet.id, rows)
    requests.append(
        _freeze_panes_request(worksheet.id, frozen_rows=1, frozen_columns=min(2, len(header)))
    )  # 西暦年・1つ目の系列
    return worksheet, requests, header


def _cell_value(value: object) -> object:
    return "" if value is None else value


def _money_column_format_requests(worksheet_id: int, rows: list[list[object]]) -> list[dict]:
    """ヘッダー行付きテーブルの金額列にカンマ区切りの表示形式を設定するリクエストを作る（1行目をヘッダーとみなす）。"""

    if not rows:
        return []
    header = [str(h) for h in rows[0]]
    return money_column_format_requests(worksheet_id, header, 1, len(rows))


def _money_row_format_requests(worksheet_id: int, rows: list[list[object]]) -> list[dict]:
    """縦持ち(A列=ラベル/B列=値)シートの金額行にカンマ区切りの表示形式を設定するリクエストを作る。"""

    row_labels = [str(row[0]) if row else "" for row in rows]
    return money_row_format_requests(worksheet_id, row_labels)


CLEAR_FORMAT_ROW_COUNT = 500
CLEAR_FORMAT_COL_COUNT = 30


def _get_or_create_worksheet(
    spreadsheet: gspread.Spreadsheet, sheet_name: str, rows: list[list[object]]
) -> tuple[gspread.Worksheet, list[dict]]:
    """シートを取得（なければ作成）し、そのシートに追加で積むべきリクエスト（既存シートの場合は
    表示形式クリア）を合わせて返す。呼び出し元はこのリクエストを他の書式・グラフ等のリクエストと
    まとめて1回のbatch_update()で送ることで、Google Sheets APIの呼び出し回数を抑える。
    """

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
        # worksheet.clear()は値のみを消し、書式（数値の表示形式等）は残る。列構成が実行のたびに
        # 変わりうる出力シート（純資産推移の内訳列、モンテカルロ等）では、以前の実行で別の列に
        # 付けたカンマ区切り表示形式が新しい列構成に残存してしまう（例: 列がずれて年の列に
        # カンマ書式が残る）ため、書き込み前に明示的に表示形式をクリアする。
        return worksheet, [_clear_number_format_request(worksheet.id)]
    except gspread.exceptions.WorksheetNotFound:
        # ダッシュボードのような縦持ちシートは先頭行(rows[0])より後方の行の方が列数が多いことがある
        # （資産配分表・純資産推移表がA/B2列のサマリより右まで伸びるため）ため、全行の最大列数を見る。
        cols = max((len(row) for row in rows), default=2)
        cols = max(cols, 2)
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=max(len(rows), 10), cols=cols)
        return worksheet, []


def _clear_number_format_request(sheet_id: int) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": CLEAR_FORMAT_ROW_COUNT,
                "startColumnIndex": 0,
                "endColumnIndex": CLEAR_FORMAT_COL_COUNT,
            },
            "cell": {"userEnteredFormat": {"numberFormat": None}},
            "fields": "userEnteredFormat.numberFormat",
        }
    }


def _resize_request(sheet_id: int, rows: Optional[int] = None, cols: Optional[int] = None) -> dict:
    """worksheet.resize()相当のリクエストをbatch_update用のdictとして組み立てる
    （即座にAPI呼び出しするworksheet.resize()の代わりに、他のリクエストとまとめて送るため）。
    """

    grid_properties: dict[str, int] = {}
    if rows is not None:
        grid_properties["rowCount"] = rows
    if cols is not None:
        grid_properties["columnCount"] = cols
    fields = ",".join(f"gridProperties.{p}" for p in grid_properties)
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": grid_properties},
            "fields": fields,
        }
    }


def _sheet_state(spreadsheet: gspread.Spreadsheet, sheet_id: int) -> dict:
    """指定シートの現在のメタデータ（charts/conditionalFormats）をfetch_sheet_metadata()の
    1回の呼び出しでまとめて取得する。チャートの張り替えと条件付き書式の張り替えを両方行うシート
    （出力_月次詳細・出力_ダッシュボード）で、個別に同じ内容を2回読みに行かないようにするため
    （Google Sheets APIの読み取り回数上限に達しやすい問題への対策）。
    """

    metadata = spreadsheet.fetch_sheet_metadata()
    for sheet in metadata.get("sheets", []):
        if sheet["properties"]["sheetId"] == sheet_id:
            return sheet
    return {"charts": [], "conditionalFormats": []}


def _native_chart_requests(
    worksheet: gspread.Worksheet,
    sheet_state: dict,
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
) -> list[dict]:
    """指定タイトルのチャートを削除して新しく作り直すリクエスト一覧を返す（既存チャートの更新の
    代わりに削除→再作成する方が、系列の増減等を含めた差分をシンプルに扱える）。

    num_rows/num_seriesはヘッダー行込みの行数・系列数の基本形（domain=列0、系列=列1..num_series、
    アンカーは表の右側）。1枚のシートに複数の表・チャートを配置する場合（純資産推移の内訳、
    モンテカルロ/ヒストリカルの統合等）は、row_start/domain_col/series_cols/anchor_row/anchor_colで
    データ範囲・アンカー位置を明示的に指定する。sheet_stateは_sheet_state()の戻り値（既存チャートの
    有無をAPI呼び出しなしで判定するために使う）。
    """

    sheet_id = worksheet.id
    series_cols = series_cols if series_cols is not None else list(range(1, num_series + 1))
    anchor_col = anchor_col if anchor_col is not None else num_series + 2
    row_end = row_start + num_rows

    requests: list[dict] = []

    # チャートのアンカーセルがグリッド範囲外だとAPIエラーになるため、データ列より右側に余白を確保する。
    required_cols = anchor_col + 10
    if worksheet.col_count < required_cols:
        requests.append(_resize_request(sheet_id, cols=required_cols))

    requests += [
        {"deleteEmbeddedObject": {"objectId": chart_id}} for chart_id in _chart_ids_in_state(sheet_state, title)
    ]

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

    requests.append(
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
    )
    return requests


def _chart_ids_in_state(sheet_state: dict, title: str) -> list[int]:
    return [
        chart["chartId"]
        for chart in sheet_state.get("charts", [])
        if chart.get("spec", {}).get("title") == title
    ]


def _heatmap_conditional_format_requests(
    sheet_id: int,
    sheet_state: dict,
    num_data_rows: int,
    num_data_cols: int,
) -> list[dict]:
    # 削除するたびにindexが詰まるため、常にindex=0を指定すればよい。
    requests = [
        {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}
        for _ in range(_conditional_format_rule_count_in_state(sheet_state))
    ]

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

    return requests


def _column_letter(index: int) -> str:
    """0始まりの列インデックスをA1表記の列名(A, B, ..., Z, AA, ...)に変換する。"""

    index += 1
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _conditional_format_rule_count_in_state(sheet_state: dict) -> int:
    return len(sheet_state.get("conditionalFormats", []))


def _dashboard_conditional_format_requests(
    sheet_id: int, sheet_state: dict, depletion_age_row: int, surplus_row: int
) -> list[dict]:
    """資産枯渇年齢・目標資産との余裕のセルを、健全(枯渇なし・余裕がプラス)なら緑、
    危険(枯渇あり・余裕がマイナス)なら赤の背景色にする条件付き書式リクエストを作る。
    行番号(0始まり)はwrite_dashboard内で常に固定（先頭7行のサマリ構造は不変）のため引数で受け取る。
    """

    # 削除するたびにindexが詰まるため、常にindex=0を指定すればよい。
    requests = [
        {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}
        for _ in range(_conditional_format_rule_count_in_state(sheet_state))
    ]

    def _value_cell_range(row: int) -> dict:
        return {"sheetId": sheet_id, "startRowIndex": row, "endRowIndex": row + 1, "startColumnIndex": 1, "endColumnIndex": 2}

    depletion_age_cell = f"$B{depletion_age_row + 1}"
    requests.append(
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [_value_cell_range(depletion_age_row)],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": DASHBOARD_NO_DEPLETION_TEXT}]},
                        "format": {"backgroundColor": DASHBOARD_HEALTHY_CELL_COLOR},
                    },
                },
                "index": 0,
            }
        }
    )
    requests.append(
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [_value_cell_range(depletion_age_row)],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f"=ISNUMBER({depletion_age_cell})"}]},
                        "format": {"backgroundColor": DASHBOARD_DANGER_CELL_COLOR},
                    },
                },
                "index": 1,
            }
        }
    )
    requests.append(
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [_value_cell_range(surplus_row)],
                    "booleanRule": {
                        "condition": {"type": "NUMBER_GREATER_THAN_EQ", "values": [{"userEnteredValue": "0"}]},
                        "format": {"backgroundColor": DASHBOARD_HEALTHY_CELL_COLOR},
                    },
                },
                "index": 2,
            }
        }
    )
    requests.append(
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [_value_cell_range(surplus_row)],
                    "booleanRule": {
                        "condition": {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "0"}]},
                        "format": {"backgroundColor": DASHBOARD_DANGER_CELL_COLOR},
                    },
                },
                "index": 3,
            }
        }
    )

    return requests


def _freeze_panes_request(sheet_id: int, frozen_rows: int, frozen_columns: int) -> dict:
    """ヘッダー行と左端のID・キー列を固定するリクエストを作る（右/下にスクロールしても常に見える
    ようにする。全シートで一貫した操作性にするため、出力シート側もこのヘルパーで統一する）。
    """

    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {
                    "frozenRowCount": frozen_rows,
                    "frozenColumnCount": frozen_columns,
                },
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    }


def _shortfall_conditional_format_requests(
    sheet_id: int, sheet_state: dict, header: list[str], row_count: int
) -> list[dict]:
    """取り崩し不足額(SHORTFALL_HEADER列)が0より大きい月（口座残高を取り崩してもなお賄いきれず、
    本当に資産が足りていない月）の行全体を赤系の背景色にする条件付き書式リクエストを作る。

    収支(NET_CASHFLOW_HEADER)がマイナスであること自体はFIRE後の取り崩し局面では正常な状態のため、
    それだけでは判定しない（収支マイナス基準だとほとんどの月が赤くなり、本当に危険な月が埋もれる）。
    """

    requests = [
        {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}
        for _ in range(_conditional_format_rule_count_in_state(sheet_state))
    ]

    if row_count > 1 and SHORTFALL_HEADER in header:
        shortfall_col_letter = _column_letter(header.index(SHORTFALL_HEADER))
        requests.append(
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": 0,
                                "endColumnIndex": len(header),
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": f"=${shortfall_col_letter}2>0"}],
                            },
                            "format": {"backgroundColor": SHORTFALL_CELL_COLOR},
                        },
                    },
                    "index": 0,
                }
            }
        )

    return requests
