from __future__ import annotations

import gspread

from adapters.sheets.sheet_mapping import OUTPUT_NETWORTH_SHEET
from core.domain.simulation_result import SimulationResult


def write_networth_table(spreadsheet: gspread.Spreadsheet, simulation_result: SimulationResult) -> None:
    rows: list[list[object]] = [["year", "networth"]]
    rows += [
        [projection.year, int(projection.networth.amount)]
        for projection in simulation_result.yearly_projections
    ]

    try:
        worksheet = spreadsheet.worksheet(OUTPUT_NETWORTH_SHEET)
        worksheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=OUTPUT_NETWORTH_SHEET, rows=max(len(rows), 10), cols=2
        )
    worksheet.update(values=rows, range_name="A1")
