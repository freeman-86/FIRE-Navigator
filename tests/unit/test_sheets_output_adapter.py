import unittest

import gspread

from adapters.sheets import sheets_output_adapter as output_adapter
from adapters.sheets.sheet_mapping import (
    AGE_HEADER,
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    CAPITAL_GAINS_TAX_HEADER,
    DASHBOARD_ALLOCATION_WEIGHT_HEADER,
    DASHBOARD_CURRENT_NETWORTH_LABEL,
    DASHBOARD_DEPLETION_AGE_LABEL,
    DASHBOARD_HISTORICAL_SUCCESS_LABEL,
    DASHBOARD_MONTECARLO_REFERENCE_1971_LABEL,
    DASHBOARD_MONTECARLO_SUCCESS_LABEL,
    DASHBOARD_NO_DEPLETION_TEXT,
    DASHBOARD_SURPLUS_LABEL,
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
    OUTPUT_SENSITIVITY_ANALYSIS_SHEET,
    P10_HEADER,
    P50_HEADER,
    P90_HEADER,
    SHORTFALL_HEADER,
    TOTAL_EXPENSE_HEADER,
    YEAR_HEADER,
)
from core.domain.montecarlo_result import MonteCarloResult, PercentileBand
from core.domain.simulation_result import MonthlyProjection, SimulationResult, YearlyProjection
from core.domain.value_objects import Money, Rate


class _FakeWorksheet:
    _next_id = 1

    def __init__(self, title: str):
        self.title = title
        self.id = _FakeWorksheet._next_id
        _FakeWorksheet._next_id += 1
        self.row_count = 10
        self.col_count = 5
        self.cleared = False
        self.updates: list[tuple[list, str]] = []

    def clear(self):
        self.cleared = True
        self.updates = []

    def update(self, values, range_name):
        self.updates.append((values, range_name))

    def resize(self, rows=None, cols=None):
        if rows is not None:
            self.row_count = rows
        if cols is not None:
            self.col_count = cols

    @property
    def last_values(self):
        return self.updates[0][0] if self.updates else None


class _FakeSpreadsheet:
    def __init__(self):
        self._worksheets: dict[str, _FakeWorksheet] = {}
        self.batch_updates: list[dict] = []
        self.charts_by_sheet_id: dict[int, list[dict]] = {}
        self.conditional_formats_by_sheet_id: dict[int, list[dict]] = {}

    def worksheet(self, name):
        if name not in self._worksheets:
            raise gspread.exceptions.WorksheetNotFound(name)
        return self._worksheets[name]

    def add_worksheet(self, title, rows, cols):
        worksheet = _FakeWorksheet(title)
        worksheet.row_count = rows
        worksheet.col_count = cols
        self._worksheets[title] = worksheet
        return worksheet

    def batch_update(self, body):
        self.batch_updates.append(body)
        for request in body["requests"]:
            if "addChart" in request:
                spec = request["addChart"]["chart"]["spec"]
                sheet_id = request["addChart"]["chart"]["position"]["overlayPosition"]["anchorCell"]["sheetId"]
                chart_id = len(self.batch_updates) * 1000 + len(request)
                self.charts_by_sheet_id.setdefault(sheet_id, []).append(
                    {"chartId": chart_id, "spec": spec}
                )
            elif "deleteEmbeddedObject" in request:
                object_id = request["deleteEmbeddedObject"]["objectId"]
                for charts in self.charts_by_sheet_id.values():
                    charts[:] = [c for c in charts if c["chartId"] != object_id]
            elif "addConditionalFormatRule" in request:
                sheet_id = request["addConditionalFormatRule"]["rule"]["ranges"][0]["sheetId"]
                self.conditional_formats_by_sheet_id.setdefault(sheet_id, []).insert(0, request)
            elif "deleteConditionalFormatRule" in request:
                sheet_id = request["deleteConditionalFormatRule"]["sheetId"]
                rules = self.conditional_formats_by_sheet_id.setdefault(sheet_id, [])
                if rules:
                    rules.pop(0)

    def fetch_sheet_metadata(self):
        return {
            "sheets": [
                {
                    "properties": {"sheetId": worksheet.id},
                    "charts": self.charts_by_sheet_id.get(worksheet.id, []),
                    "conditionalFormats": self.conditional_formats_by_sheet_id.get(worksheet.id, []),
                }
                for worksheet in self._worksheets.values()
            ]
        }


def _number_format_requests(spreadsheet, sheet_id):
    return [
        r["repeatCell"]
        for body in spreadsheet.batch_updates
        for r in body["requests"]
        if "repeatCell" in r
        and r["repeatCell"]["range"]["sheetId"] == sheet_id
        and r["repeatCell"]["fields"] == "userEnteredFormat.numberFormat"
    ]


def _frozen_pane_properties(spreadsheet, sheet_id):
    # updateSheetPropertiesはグラフ用の列数拡張(resize)にも使われるため、freeze専用のfields
    # ("gridProperties.frozenRowCount,gridProperties.frozenColumnCount")で絞り込む。
    matches = [
        r["updateSheetProperties"]
        for body in spreadsheet.batch_updates
        for r in body["requests"]
        if "updateSheetProperties" in r
        and r["updateSheetProperties"]["properties"]["sheetId"] == sheet_id
        and r["updateSheetProperties"]["fields"] == "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
    ]
    assert len(matches) == 1
    return matches[0]["properties"]["gridProperties"]


def _projection(year: int, networth: int) -> YearlyProjection:
    return YearlyProjection(
        year=year,
        age_self=36,
        gross_income=Money.zero(),
        pension_income=Money.zero(),
        income_tax=Money.zero(),
        resident_tax=Money.zero(),
        social_insurance=Money.zero(),
        net_income=Money.zero(),
        total_expense=Money.zero(),
        net_cashflow=Money.zero(),
        account_balances={},
        networth=Money.of(networth),
    )


class WriteDashboardTest(unittest.TestCase):
    def test_writes_summary_rows(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        dashboard = {
            "current_networth": Money.of(30_000_000),
            "extra_annual_budget": Money.of(300_000),
            "extra_monthly_budget": Money.of(25_000),
            "depletion_age": None,
            "target_ending_networth": Money.zero(),
            "ending_networth": Money.of(21_000_000),
            "surplus_vs_target": Money.of(21_000_000),
        }

        output_adapter.write_dashboard(spreadsheet, dashboard)

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        rows = dict(worksheet.last_values)
        self.assertEqual(rows[DASHBOARD_CURRENT_NETWORTH_LABEL], 30_000_000)
        self.assertEqual(rows[DASHBOARD_DEPLETION_AGE_LABEL], DASHBOARD_NO_DEPLETION_TEXT)

    def test_writes_depletion_age_when_present(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        dashboard = {
            "current_networth": Money.of(1_000_000),
            "extra_annual_budget": Money.zero(),
            "extra_monthly_budget": Money.zero(),
            "depletion_age": 78,
            "target_ending_networth": Money.zero(),
            "ending_networth": Money.of(-500_000),
            "surplus_vs_target": Money.of(-500_000),
        }

        output_adapter.write_dashboard(spreadsheet, dashboard)

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        rows = dict(worksheet.last_values)
        self.assertEqual(rows[DASHBOARD_DEPLETION_AGE_LABEL], 78)

    def test_money_rows_get_comma_number_format_but_depletion_age_row_does_not(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        dashboard = {
            "current_networth": Money.of(30_000_000),
            "extra_annual_budget": Money.of(300_000),
            "extra_monthly_budget": Money.of(25_000),
            "depletion_age": 78,
            "target_ending_networth": Money.zero(),
            "ending_networth": Money.of(21_000_000),
            "surplus_vs_target": Money.of(21_000_000),
        }

        output_adapter.write_dashboard(spreadsheet, dashboard)

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        number_format_requests = _number_format_requests(spreadsheet, worksheet.id)
        formatted_rows = {r["range"]["startRowIndex"] for r in number_format_requests}

        self.assertIn(0, formatted_rows)  # DASHBOARD_CURRENT_NETWORTH_LABEL
        depletion_age_row = [row[0] for row in worksheet.last_values].index(DASHBOARD_DEPLETION_AGE_LABEL)
        self.assertNotIn(depletion_age_row, formatted_rows)

    def _base_dashboard(self, depletion_age=None, surplus=21_000_000) -> dict:
        return {
            "current_networth": Money.of(30_000_000),
            "extra_annual_budget": Money.of(300_000),
            "extra_monthly_budget": Money.of(25_000),
            "depletion_age": depletion_age,
            "target_ending_networth": Money.zero(),
            "ending_networth": Money.of(21_000_000),
            "surplus_vs_target": Money.of(surplus),
        }

    def test_healthy_depletion_and_surplus_get_green_conditional_format(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_dashboard(spreadsheet, self._base_dashboard(depletion_age=None, surplus=21_000_000))

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        rules = spreadsheet.conditional_formats_by_sheet_id[worksheet.id]
        self.assertEqual(len(rules), 4)
        healthy_rules = [
            r["addConditionalFormatRule"]["rule"]
            for r in rules
            if r["addConditionalFormatRule"]["rule"]["booleanRule"]["format"]["backgroundColor"]
            == output_adapter.DASHBOARD_HEALTHY_CELL_COLOR
        ]
        self.assertEqual(len(healthy_rules), 2)

    def test_rerunning_does_not_duplicate_conditional_format_rules(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_dashboard(spreadsheet, self._base_dashboard())
        output_adapter.write_dashboard(spreadsheet, self._base_dashboard())

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        self.assertEqual(len(spreadsheet.conditional_formats_by_sheet_id[worksheet.id]), 4)

    def test_writes_montecarlo_and_historical_success_rate_rows(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        montecarlo = MonteCarloResult(trials=100, success_count=87, success_rate=0.87)
        historical = MonteCarloResult(trials=50, success_count=40, success_rate=0.8)

        output_adapter.write_dashboard(
            spreadsheet, self._base_dashboard(), montecarlo=montecarlo, historical=historical
        )

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        rows = dict(worksheet.last_values[:9])
        self.assertIn("87.0%", rows[DASHBOARD_MONTECARLO_SUCCESS_LABEL])
        self.assertIn("87/100", rows[DASHBOARD_MONTECARLO_SUCCESS_LABEL])
        self.assertIn("80.0%", rows[DASHBOARD_HISTORICAL_SUCCESS_LABEL])

    def test_writes_montecarlo_reference_1971_row_between_main_montecarlo_and_historical(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        montecarlo = MonteCarloResult(trials=100, success_count=87, success_rate=0.87)
        reference_1971 = MonteCarloResult(trials=100, success_count=91, success_rate=0.91)
        historical = MonteCarloResult(trials=50, success_count=40, success_rate=0.8)

        output_adapter.write_dashboard(
            spreadsheet,
            self._base_dashboard(),
            montecarlo=montecarlo,
            historical=historical,
            montecarlo_reference_1971=reference_1971,
        )

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        values = worksheet.last_values
        rows = dict(values[:10])
        self.assertIn("91.0%", rows[DASHBOARD_MONTECARLO_REFERENCE_1971_LABEL])
        self.assertIn("91/100", rows[DASHBOARD_MONTECARLO_REFERENCE_1971_LABEL])
        # メインのモンテカルロ→参考値(1971年以降)→ヒストリカルの順で並ぶ
        labels = [row[0] for row in values]
        self.assertEqual(
            labels.index(DASHBOARD_MONTECARLO_REFERENCE_1971_LABEL),
            labels.index(DASHBOARD_MONTECARLO_SUCCESS_LABEL) + 1,
        )
        self.assertEqual(
            labels.index(DASHBOARD_HISTORICAL_SUCCESS_LABEL),
            labels.index(DASHBOARD_MONTECARLO_REFERENCE_1971_LABEL) + 1,
        )

    def test_no_montecarlo_reference_1971_row_when_omitted(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_dashboard(spreadsheet, self._base_dashboard())

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        labels = [row[0] for row in worksheet.last_values]
        self.assertNotIn(DASHBOARD_MONTECARLO_REFERENCE_1971_LABEL, labels)

    def test_writes_asset_allocation_table_with_percent_format(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        dashboard = self._base_dashboard()
        dashboard["asset_allocation"] = [
            {"asset_class": "equity_sp500", "amount": Money.of(7_000_000), "weight": Rate.of("0.7")},
            {"asset_class": "cash", "amount": Money.of(3_000_000), "weight": Rate.of("0.3")},
        ]

        output_adapter.write_dashboard(spreadsheet, dashboard)

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        values = worksheet.last_values
        header_row = [ASSET_CLASS_HEADER, BALANCE_HEADER, DASHBOARD_ALLOCATION_WEIGHT_HEADER]
        self.assertIn(header_row, values)
        self.assertIn(["equity_sp500", 7_000_000, 0.7], values)

        percent_requests = [
            r["repeatCell"]
            for body in spreadsheet.batch_updates
            for r in body["requests"]
            if "repeatCell" in r and r["repeatCell"]["cell"]["userEnteredFormat"].get("numberFormat", {}).get("type") == "PERCENT"
        ]
        self.assertTrue(percent_requests)

    def test_embeds_networth_line_chart_when_simulation_result_given(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        result = SimulationResult(yearly_projections=[_projection(2026, 1_000_000), _projection(2027, 2_000_000)])

        output_adapter.write_dashboard(spreadsheet, self._base_dashboard(), simulation_result=result)

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        charts = spreadsheet.charts_by_sheet_id[worksheet.id]
        self.assertEqual(len(charts), 1)
        self.assertEqual(charts[0]["spec"]["title"], output_adapter.DASHBOARD_NETWORTH_CHART_TITLE)
        self.assertEqual(charts[0]["spec"]["basicChart"]["chartType"], "LINE")
        self.assertNotIn("stackedType", charts[0]["spec"]["basicChart"])

    def test_no_chart_when_simulation_result_omitted(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_dashboard(spreadsheet, self._base_dashboard())

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        self.assertNotIn(worksheet.id, spreadsheet.charts_by_sheet_id)

    def test_freezes_label_column_but_not_a_header_row(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_dashboard(spreadsheet, self._base_dashboard())

        worksheet = spreadsheet.worksheet(OUTPUT_DASHBOARD_SHEET)
        grid_properties = _frozen_pane_properties(spreadsheet, worksheet.id)
        self.assertEqual(grid_properties["frozenRowCount"], 0)
        self.assertEqual(grid_properties["frozenColumnCount"], 1)


def _breakdown_chart() -> dict:
    return {
        "x": [2026, 2027],
        "series": [
            {"name": "taxable", "values": [1_000_000, 1_100_000]},
            {"name": "nisa_growth", "values": [500_000, None]},
        ],
    }


class WriteNetworthTableTest(unittest.TestCase):
    def test_writes_year_networth_and_breakdown_columns(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        result = SimulationResult(yearly_projections=[_projection(2026, 1_000_000), _projection(2027, 2_000_000)])

        output_adapter.write_networth_table(spreadsheet, result, _breakdown_chart())

        worksheet = spreadsheet.worksheet(OUTPUT_NETWORTH_SHEET)
        self.assertEqual(
            worksheet.last_values,
            [
                [YEAR_HEADER, NETWORTH_HEADER, CAPITAL_GAINS_TAX_HEADER, "taxable", "nisa_growth"],
                [2026, 1_000_000, 0, 1_000_000, 500_000],
                [2027, 2_000_000, 0, 1_100_000, ""],
            ],
        )

        number_format_requests = _number_format_requests(spreadsheet, worksheet.id)
        formatted_columns = {r["range"]["startColumnIndex"] for r in number_format_requests}
        self.assertEqual(formatted_columns, {1, 2, 3, 4})  # YEAR(0)は対象外、内訳列(3,4)も金額として対象

        charts = spreadsheet.charts_by_sheet_id[worksheet.id]
        self.assertEqual(len(charts), 1)
        self.assertEqual(charts[0]["spec"]["title"], output_adapter.BREAKDOWN_CHART_TITLE)
        self.assertEqual(charts[0]["spec"]["basicChart"]["stackedType"], "STACKED")

        grid_properties = _frozen_pane_properties(spreadsheet, worksheet.id)
        self.assertEqual(grid_properties["frozenRowCount"], 1)
        self.assertEqual(grid_properties["frozenColumnCount"], 2)  # 西暦年・純資産

    def test_rerunning_does_not_duplicate_chart(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        result = SimulationResult(yearly_projections=[_projection(2026, 1_000_000), _projection(2027, 2_000_000)])

        output_adapter.write_networth_table(spreadsheet, result, _breakdown_chart())
        output_adapter.write_networth_table(spreadsheet, result, _breakdown_chart())

        worksheet = spreadsheet.worksheet(OUTPUT_NETWORTH_SHEET)
        self.assertEqual(len(spreadsheet.charts_by_sheet_id[worksheet.id]), 1)

    def test_no_breakdown_series_skips_chart(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        result = SimulationResult(yearly_projections=[_projection(2026, 1_000_000)])

        output_adapter.write_networth_table(spreadsheet, result, {"x": [2026], "series": []})

        worksheet = spreadsheet.worksheet(OUTPUT_NETWORTH_SHEET)
        self.assertEqual(
            worksheet.last_values,
            [[YEAR_HEADER, NETWORTH_HEADER, CAPITAL_GAINS_TAX_HEADER], [2026, 1_000_000, 0]],
        )
        self.assertNotIn(worksheet.id, spreadsheet.charts_by_sheet_id)


def _monthly_projection(
    year: int, month: int, networth: int, capital_gains_tax: int = 0, remaining_shortfall: int = 0
) -> MonthlyProjection:
    return MonthlyProjection(
        year=year,
        month=month,
        age_self=36,
        gross_income=Money.zero(),
        pension_income=Money.zero(),
        net_income=Money.of(300_000),
        total_expense=Money.of(250_000),
        net_cashflow=Money.of(50_000),
        capital_gains_tax=Money.of(capital_gains_tax),
        account_balances={},
        networth=Money.of(networth),
        remaining_shortfall=Money.of(remaining_shortfall),
    )


class WriteMonthlyDetailTableTest(unittest.TestCase):
    def test_writes_one_row_per_monthly_projection(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        result = SimulationResult(
            monthly_projections=[
                _monthly_projection(2026, 1, 1_050_000),
                _monthly_projection(2026, 2, 1_100_000, capital_gains_tax=5_000),
            ]
        )

        output_adapter.write_monthly_detail_table(spreadsheet, result)

        worksheet = spreadsheet.worksheet(OUTPUT_MONTHLY_DETAIL_SHEET)
        self.assertEqual(
            worksheet.last_values,
            [
                [YEAR_HEADER, MONTH_HEADER, AGE_HEADER, NET_INCOME_HEADER, TOTAL_EXPENSE_HEADER,
                 NET_CASHFLOW_HEADER, CAPITAL_GAINS_TAX_HEADER, SHORTFALL_HEADER, NETWORTH_HEADER],
                [2026, 1, 36, 300_000, 250_000, 50_000, 0, 0, 1_050_000],
                [2026, 2, 36, 300_000, 250_000, 50_000, 5_000, 0, 1_100_000],
            ],
        )

        worksheet = spreadsheet.worksheet(OUTPUT_MONTHLY_DETAIL_SHEET)
        number_format_requests = _number_format_requests(spreadsheet, worksheet.id)
        formatted_columns = {r["range"]["startColumnIndex"] for r in number_format_requests}
        # YEAR(0)/MONTH(1)/AGE(2)は対象外、手取り収入以降(3〜8)が金額列
        self.assertEqual(formatted_columns, {3, 4, 5, 6, 7, 8})

    def test_appends_dynamic_asset_class_withdrawal_columns(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        projection = _monthly_projection(2026, 1, 1_050_000)
        projection.withdrawals_by_asset_class = {
            "equity_sp500": Money.of(80_000),
            "bond_us_treasury": Money.zero(),
        }
        result = SimulationResult(monthly_projections=[projection])

        output_adapter.write_monthly_detail_table(spreadsheet, result)

        worksheet = spreadsheet.worksheet(OUTPUT_MONTHLY_DETAIL_SHEET)
        header, row = worksheet.last_values
        self.assertEqual(header[-2:], ["bond_us_treasury", "equity_sp500"])
        self.assertEqual(row[-2:], [0, 80_000])

    def test_freezes_header_row_and_leading_columns(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        result = SimulationResult(monthly_projections=[_monthly_projection(2026, 1, 1_050_000)])

        output_adapter.write_monthly_detail_table(spreadsheet, result)

        worksheet = spreadsheet.worksheet(OUTPUT_MONTHLY_DETAIL_SHEET)
        grid_properties = _frozen_pane_properties(spreadsheet, worksheet.id)
        self.assertEqual(grid_properties["frozenRowCount"], 1)
        self.assertEqual(grid_properties["frozenColumnCount"], 3)

    def test_shortfall_month_gets_conditional_format_rule(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        # 収支はプラスでも（口座からの取り崩しで賄えている月と区別するため）、取り崩しきれずに
        # 残った不足額(remaining_shortfall)が0より大きい月だけが赤くなることを確認する。
        shortfall_month = MonthlyProjection(
            year=2026, month=1, age_self=98, gross_income=Money.zero(), pension_income=Money.zero(),
            net_income=Money.of(200_000), total_expense=Money.of(300_000), net_cashflow=Money.of(-100_000),
            account_balances={}, networth=Money.zero(), remaining_shortfall=Money.of(100_000),
        )
        result = SimulationResult(monthly_projections=[shortfall_month])

        output_adapter.write_monthly_detail_table(spreadsheet, result)

        worksheet = spreadsheet.worksheet(OUTPUT_MONTHLY_DETAIL_SHEET)
        rules = spreadsheet.conditional_formats_by_sheet_id[worksheet.id]
        self.assertEqual(len(rules), 1)
        rule = rules[0]["addConditionalFormatRule"]["rule"]
        formula = rule["booleanRule"]["condition"]["values"][0]["userEnteredValue"]
        self.assertIn(">0", formula)
        self.assertIn("$H", formula)  # SHORTFALL_HEADER列（0始まりindex7 = H列）
        self.assertNotIn("$F", formula)  # NET_CASHFLOW_HEADER列(F列)は判定に使わない
        self.assertEqual(rule["ranges"][0]["endColumnIndex"], 9)  # 動的な資産クラス列がない場合は9列分

    def test_rerunning_does_not_duplicate_negative_cashflow_rule(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        result = SimulationResult(monthly_projections=[_monthly_projection(2026, 1, 1_050_000)])

        output_adapter.write_monthly_detail_table(spreadsheet, result)
        output_adapter.write_monthly_detail_table(spreadsheet, result)

        worksheet = spreadsheet.worksheet(OUTPUT_MONTHLY_DETAIL_SHEET)
        self.assertEqual(len(spreadsheet.conditional_formats_by_sheet_id[worksheet.id]), 1)

    def test_embeds_monthly_networth_line_chart(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        result = SimulationResult(
            monthly_projections=[_monthly_projection(2026, 1, 1_050_000), _monthly_projection(2026, 2, 1_100_000)]
        )

        output_adapter.write_monthly_detail_table(spreadsheet, result)

        worksheet = spreadsheet.worksheet(OUTPUT_MONTHLY_DETAIL_SHEET)
        charts = spreadsheet.charts_by_sheet_id[worksheet.id]
        self.assertEqual(len(charts), 1)
        self.assertEqual(charts[0]["spec"]["title"], output_adapter.MONTHLY_NETWORTH_CHART_TITLE)
        self.assertEqual(charts[0]["spec"]["basicChart"]["chartType"], "LINE")


class WriteChartsTest(unittest.TestCase):
    def _chart(self) -> dict:
        return {
            "x": [2026, 2027],
            "series": [
                {"name": "taxable", "values": [1_000_000, 1_100_000]},
                {"name": "nisa_growth", "values": [500_000, None]},
            ],
        }

    def test_progress_comparison_chart_is_not_stacked(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_progress_comparison(spreadsheet, self._chart())

        worksheet = spreadsheet.worksheet(OUTPUT_PROGRESS_COMPARISON_SHEET)
        charts = spreadsheet.charts_by_sheet_id[worksheet.id]
        self.assertNotIn("stackedType", charts[0]["spec"]["basicChart"])
        self.assertEqual(charts[0]["spec"]["basicChart"]["chartType"], "LINE")

    def test_freezes_header_row_and_year_and_first_series_columns(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_progress_comparison(spreadsheet, self._chart())

        worksheet = spreadsheet.worksheet(OUTPUT_PROGRESS_COMPARISON_SHEET)
        grid_properties = _frozen_pane_properties(spreadsheet, worksheet.id)
        self.assertEqual(grid_properties["frozenRowCount"], 1)
        self.assertEqual(grid_properties["frozenColumnCount"], 2)  # 西暦年・1つ目の系列

    def test_freezes_only_available_columns_when_chart_has_no_series(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_progress_comparison(spreadsheet, {"x": [2026], "series": []})

        worksheet = spreadsheet.worksheet(OUTPUT_PROGRESS_COMPARISON_SHEET)
        grid_properties = _frozen_pane_properties(spreadsheet, worksheet.id)
        self.assertEqual(grid_properties["frozenColumnCount"], 1)  # 西暦年列しかないため1列に収まる


class WriteSensitivityTableTest(unittest.TestCase):
    def test_writes_grid_and_conditional_format(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        table = {
            "row_labels": ["-1%", "+1%"],
            "column_labels": ["-0.5%", "+0.5%"],
            "cells": [[100, 200], [300, 400]],
        }

        output_adapter.write_sensitivity_table(spreadsheet, table)

        worksheet = spreadsheet.worksheet(OUTPUT_SENSITIVITY_ANALYSIS_SHEET)
        self.assertEqual(
            worksheet.last_values,
            [
                [output_adapter.SENSITIVITY_TABLE_HEADER, "-0.5%", "+0.5%"],
                ["-1%", 100, 200],
                ["+1%", 300, 400],
            ],
        )
        self.assertEqual(len(spreadsheet.conditional_formats_by_sheet_id[worksheet.id]), 1)

        grid_properties = _frozen_pane_properties(spreadsheet, worksheet.id)
        self.assertEqual(grid_properties["frozenRowCount"], 1)
        self.assertEqual(grid_properties["frozenColumnCount"], 1)

    def test_rerunning_does_not_duplicate_conditional_format(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        table = {"row_labels": ["±0%"], "column_labels": ["±0%"], "cells": [[100]]}

        output_adapter.write_sensitivity_table(spreadsheet, table)
        output_adapter.write_sensitivity_table(spreadsheet, table)

        worksheet = spreadsheet.worksheet(OUTPUT_SENSITIVITY_ANALYSIS_SHEET)
        self.assertEqual(len(spreadsheet.conditional_formats_by_sheet_id[worksheet.id]), 1)


def _percentile_result(trials: int, success_count: int, success_rate: float) -> MonteCarloResult:
    return MonteCarloResult(
        trials=trials,
        success_count=success_count,
        success_rate=success_rate,
        percentile_networth_by_year={
            2026: PercentileBand(p10=Money.of(1_000_000), p50=Money.of(2_000_000), p90=Money.of(3_000_000))
        },
    )


def _percentile_chart() -> dict:
    return {"x": [2026], "p10": [1_000_000], "p50": [2_000_000], "p90": [3_000_000]}


class WriteMontecarloAndHistoricalResultTest(unittest.TestCase):
    def test_writes_both_methods_with_method_column_and_two_charts(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        montecarlo_result = _percentile_result(100, 87, 0.87)
        historical_result = _percentile_result(50, 40, 0.8)

        output_adapter.write_montecarlo_and_historical_result(
            spreadsheet, (montecarlo_result, _percentile_chart()), (historical_result, _percentile_chart())
        )

        worksheet = spreadsheet.worksheet(OUTPUT_MONTECARLO_SHEET)
        table_values = worksheet.updates[0][0]
        self.assertEqual(
            table_values,
            [
                [METHOD_HEADER, YEAR_HEADER, P10_HEADER, P50_HEADER, P90_HEADER],
                [MONTECARLO_METHOD_LABEL, 2026, 1_000_000, 2_000_000, 3_000_000],
                [METHOD_HEADER, YEAR_HEADER, P10_HEADER, P50_HEADER, P90_HEADER],
                [HISTORICAL_METHOD_LABEL, 2026, 1_000_000, 2_000_000, 3_000_000],
            ],
        )

        summary_values = worksheet.updates[1][0]
        self.assertIn(MONTECARLO_METHOD_LABEL, summary_values[0][0])
        self.assertIn("87.0%", summary_values[0][0])
        self.assertIn("87/100", summary_values[0][0])
        self.assertIn(HISTORICAL_METHOD_LABEL, summary_values[1][0])
        self.assertIn("80.0%", summary_values[1][0])
        self.assertIn("40/50", summary_values[1][0])

        charts = spreadsheet.charts_by_sheet_id[worksheet.id]
        self.assertEqual(len(charts), 2)
        titles = {c["spec"]["title"] for c in charts}
        self.assertEqual(titles, {output_adapter.MONTECARLO_CHART_TITLE, output_adapter.HISTORICAL_BACKTEST_CHART_TITLE})

        number_format_requests = _number_format_requests(spreadsheet, worksheet.id)
        formatted_columns = {r["range"]["startColumnIndex"] for r in number_format_requests}
        self.assertEqual(formatted_columns, {2, 3, 4})  # P10/P50/P90、METHOD(0)/YEAR(1)は対象外

        grid_properties = _frozen_pane_properties(spreadsheet, worksheet.id)
        self.assertEqual(grid_properties["frozenRowCount"], 1)
        self.assertEqual(grid_properties["frozenColumnCount"], 2)  # 手法・西暦年

    def test_writes_montecarlo_only_when_historical_is_skipped(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        montecarlo_result = _percentile_result(100, 87, 0.87)

        output_adapter.write_montecarlo_and_historical_result(spreadsheet, (montecarlo_result, _percentile_chart()), None)

        worksheet = spreadsheet.worksheet(OUTPUT_MONTECARLO_SHEET)
        table_values = worksheet.updates[0][0]
        self.assertEqual(
            table_values,
            [
                [METHOD_HEADER, YEAR_HEADER, P10_HEADER, P50_HEADER, P90_HEADER],
                [MONTECARLO_METHOD_LABEL, 2026, 1_000_000, 2_000_000, 3_000_000],
            ],
        )
        charts = spreadsheet.charts_by_sheet_id[worksheet.id]
        self.assertEqual(len(charts), 1)
        self.assertEqual(charts[0]["spec"]["title"], output_adapter.MONTECARLO_CHART_TITLE)

    def test_does_nothing_when_both_are_skipped(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_montecarlo_and_historical_result(spreadsheet, None, None)

        with self.assertRaises(gspread.exceptions.WorksheetNotFound):
            spreadsheet.worksheet(OUTPUT_MONTECARLO_SHEET)

    def test_reference_1971_summary_line_sits_between_main_montecarlo_and_historical(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        montecarlo_result = _percentile_result(100, 87, 0.87)
        historical_result = _percentile_result(50, 40, 0.8)
        reference_1971_result = _percentile_result(100, 91, 0.91)

        output_adapter.write_montecarlo_and_historical_result(
            spreadsheet,
            (montecarlo_result, _percentile_chart()),
            (historical_result, _percentile_chart()),
            reference_1971_result,
        )

        worksheet = spreadsheet.worksheet(OUTPUT_MONTECARLO_SHEET)
        summary_values = worksheet.updates[1][0]
        self.assertEqual(len(summary_values), 3)
        self.assertIn(MONTECARLO_METHOD_LABEL, summary_values[0][0])
        self.assertIn("87.0%", summary_values[0][0])
        self.assertIn(MONTECARLO_METHOD_LABEL, summary_values[1][0])
        self.assertIn("（参考: 1971年以降のデータで分布推定）", summary_values[1][0])
        self.assertIn("91.0%", summary_values[1][0])
        self.assertIn("91/100", summary_values[1][0])
        self.assertIn(HISTORICAL_METHOD_LABEL, summary_values[2][0])
        self.assertIn("80.0%", summary_values[2][0])

        # 参考行専用の表・チャートは作らない
        charts = spreadsheet.charts_by_sheet_id[worksheet.id]
        self.assertEqual(len(charts), 2)

    def test_no_reference_1971_summary_line_when_omitted(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        montecarlo_result = _percentile_result(100, 87, 0.87)
        historical_result = _percentile_result(50, 40, 0.8)

        output_adapter.write_montecarlo_and_historical_result(
            spreadsheet, (montecarlo_result, _percentile_chart()), (historical_result, _percentile_chart())
        )

        worksheet = spreadsheet.worksheet(OUTPUT_MONTECARLO_SHEET)
        summary_values = worksheet.updates[1][0]
        self.assertEqual(len(summary_values), 2)


if __name__ == "__main__":
    unittest.main()
