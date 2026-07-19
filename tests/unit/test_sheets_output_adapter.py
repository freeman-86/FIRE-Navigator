import unittest

import gspread

from adapters.sheets import sheets_output_adapter as output_adapter
from adapters.sheets.sheet_mapping import (
    DASHBOARD_CURRENT_NETWORTH_LABEL,
    DASHBOARD_DEPLETION_AGE_LABEL,
    DASHBOARD_NO_DEPLETION_TEXT,
    NETWORTH_HEADER,
    OUTPUT_DASHBOARD_SHEET,
    OUTPUT_MONTECARLO_SHEET,
    OUTPUT_NETWORTH_BREAKDOWN_SHEET,
    OUTPUT_NETWORTH_SHEET,
    OUTPUT_SCENARIO_COMPARISON_SHEET,
    OUTPUT_SENSITIVITY_ANALYSIS_SHEET,
    P10_HEADER,
    P50_HEADER,
    P90_HEADER,
    YEAR_HEADER,
)
from core.domain.montecarlo_result import MonteCarloResult, PercentileBand
from core.domain.simulation_result import SimulationResult, YearlyProjection
from core.domain.value_objects import Money


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


class WriteNetworthTableTest(unittest.TestCase):
    def test_writes_year_and_networth_rows(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        result = SimulationResult(yearly_projections=[_projection(2026, 1_000_000), _projection(2027, 2_000_000)])

        output_adapter.write_networth_table(spreadsheet, result)

        worksheet = spreadsheet.worksheet(OUTPUT_NETWORTH_SHEET)
        self.assertEqual(
            worksheet.last_values, [[YEAR_HEADER, NETWORTH_HEADER], [2026, 1_000_000], [2027, 2_000_000]]
        )


class WriteChartsTest(unittest.TestCase):
    def _chart(self) -> dict:
        return {
            "x": [2026, 2027],
            "series": [
                {"name": "taxable", "values": [1_000_000, 1_100_000]},
                {"name": "nisa_growth", "values": [500_000, None]},
            ],
        }

    def test_networth_breakdown_writes_table_and_creates_chart(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_networth_breakdown_chart(spreadsheet, self._chart())

        worksheet = spreadsheet.worksheet(OUTPUT_NETWORTH_BREAKDOWN_SHEET)
        self.assertEqual(
            worksheet.last_values,
            [[YEAR_HEADER, "taxable", "nisa_growth"], [2026, 1_000_000, 500_000], [2027, 1_100_000, ""]],
        )
        charts = spreadsheet.charts_by_sheet_id[worksheet.id]
        self.assertEqual(len(charts), 1)
        self.assertEqual(charts[0]["spec"]["title"], output_adapter.BREAKDOWN_CHART_TITLE)
        self.assertEqual(charts[0]["spec"]["basicChart"]["stackedType"], "STACKED")

    def test_rerunning_does_not_duplicate_chart(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_networth_breakdown_chart(spreadsheet, self._chart())
        output_adapter.write_networth_breakdown_chart(spreadsheet, self._chart())

        worksheet = spreadsheet.worksheet(OUTPUT_NETWORTH_BREAKDOWN_SHEET)
        self.assertEqual(len(spreadsheet.charts_by_sheet_id[worksheet.id]), 1)

    def test_scenario_comparison_chart_is_not_stacked(self) -> None:
        spreadsheet = _FakeSpreadsheet()

        output_adapter.write_scenario_comparison(spreadsheet, self._chart())

        worksheet = spreadsheet.worksheet(OUTPUT_SCENARIO_COMPARISON_SHEET)
        charts = spreadsheet.charts_by_sheet_id[worksheet.id]
        self.assertNotIn("stackedType", charts[0]["spec"]["basicChart"])
        self.assertEqual(charts[0]["spec"]["basicChart"]["chartType"], "LINE")


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

    def test_rerunning_does_not_duplicate_conditional_format(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        table = {"row_labels": ["±0%"], "column_labels": ["±0%"], "cells": [[100]]}

        output_adapter.write_sensitivity_table(spreadsheet, table)
        output_adapter.write_sensitivity_table(spreadsheet, table)

        worksheet = spreadsheet.worksheet(OUTPUT_SENSITIVITY_ANALYSIS_SHEET)
        self.assertEqual(len(spreadsheet.conditional_formats_by_sheet_id[worksheet.id]), 1)


class WritePercentileResultTest(unittest.TestCase):
    def test_writes_percentile_table_success_summary_and_chart(self) -> None:
        spreadsheet = _FakeSpreadsheet()
        result = MonteCarloResult(
            trials=100,
            success_count=87,
            success_rate=0.87,
            percentile_networth_by_year={
                2026: PercentileBand(p10=Money.of(1_000_000), p50=Money.of(2_000_000), p90=Money.of(3_000_000))
            },
        )
        chart = {"x": [2026], "p10": [1_000_000], "p50": [2_000_000], "p90": [3_000_000]}

        output_adapter.write_montecarlo_result(spreadsheet, result, chart)

        worksheet = spreadsheet.worksheet(OUTPUT_MONTECARLO_SHEET)
        table_values, summary_values = worksheet.updates[0][0], worksheet.updates[1][0]
        self.assertEqual(
            table_values,
            [[YEAR_HEADER, P10_HEADER, P50_HEADER, P90_HEADER], [2026, 1_000_000, 2_000_000, 3_000_000]],
        )
        self.assertIn("87.0%", summary_values[0][0])
        self.assertIn("87/100", summary_values[0][0])
        charts = spreadsheet.charts_by_sheet_id[worksheet.id]
        self.assertEqual(charts[0]["spec"]["title"], output_adapter.MONTECARLO_CHART_TITLE)


if __name__ == "__main__":
    unittest.main()
