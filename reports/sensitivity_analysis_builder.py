from __future__ import annotations

from core.simulation.projection.sensitivity_analysis import SensitivityResult

SENSITIVITY_TABLE_TYPE = "grid"


def build_sensitivity_table(result: SensitivityResult) -> dict:
    """成長率×インフレ率の最終ネットワースをグリッド形式（行=成長率、列=インフレ率）で生成する。"""

    rows = [
        [
            int(result.final_networth_grid[(growth_label, inflation_label)].amount)
            for inflation_label in result.inflation_rate_labels
        ]
        for growth_label in result.growth_rate_labels
    ]

    return {
        "type": SENSITIVITY_TABLE_TYPE,
        "row_axis": "investment_growth_rate",
        "column_axis": "inflation_rate",
        "row_labels": result.growth_rate_labels,
        "column_labels": result.inflation_rate_labels,
        "cells": rows,
    }
