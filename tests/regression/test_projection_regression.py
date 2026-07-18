import json
import os
import unittest

from core.simulation.projection.projection_engine import run_projection
from reports.chart_builder import build_networth_chart
from tests.regression.scenario_sprint4 import build_scenario_plan

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden", "projection_sprint4.json")


def _serialize_result(plan, simulation_result) -> dict:
    yearly_projections = [
        {
            "year": projection.year,
            "age_self": projection.age_self,
            "gross_income": int(projection.gross_income.amount),
            "total_expense": int(projection.total_expense.amount),
            "net_cashflow": int(projection.net_cashflow.amount),
            "account_balances": {
                account_id: int(balance.amount) for account_id, balance in projection.account_balances.items()
            },
            "networth": int(projection.networth.amount),
        }
        for projection in simulation_result.yearly_projections
    ]
    return {
        "config_version": "sprint4-baseline",
        "yearly_projections": yearly_projections,
        "networth_chart": build_networth_chart(plan, simulation_result),
    }


class ProjectionRegressionTest(unittest.TestCase):
    def test_fixed_scenario_matches_golden_baseline(self) -> None:
        plan = build_scenario_plan()
        result = run_projection(plan)
        actual = _serialize_result(plan, result)

        with open(GOLDEN_PATH, encoding="utf-8") as f:
            expected = json.load(f)

        self.assertEqual(
            actual,
            expected,
            "固定シナリオの計算結果がgolden fileと一致しません。意図した変更であればレビューを経てgolden fileを更新してください。",
        )


if __name__ == "__main__":
    unittest.main()
