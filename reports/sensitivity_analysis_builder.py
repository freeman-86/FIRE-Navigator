from __future__ import annotations

from core.simulation.projection.sensitivity_analysis import SensitivityResult

SENSITIVITY_TABLE_TYPE = "grid"


def build_sensitivity_table(result: SensitivityResult) -> dict:
    """支出水準増減×インフレ率の最終ネットワースをグリッド形式（行=支出水準増減、
    列=インフレ率）で生成する。"""

    rows = [
        [
            int(result.final_networth_grid[(expense_label, inflation_label)].amount)
            for inflation_label in result.inflation_rate_labels
        ]
        for expense_label in result.expense_level_labels
    ]

    return {
        "type": SENSITIVITY_TABLE_TYPE,
        "row_axis": "expense_level_delta",
        "column_axis": "inflation_rate",
        "row_labels": result.expense_level_labels,
        "column_labels": result.inflation_rate_labels,
        "cells": rows,
    }
