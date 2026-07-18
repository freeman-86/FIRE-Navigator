import json
import os
import unittest

from core.simulation.projection.projection_engine import run_projection
from repositories.config_repository import load_pension_rules, load_portfolio_rules, load_tax_rules
from reports.chart_builder import build_networth_chart
from tests.regression.scenario_sprint4 import build_scenario_plan, build_scenario_portfolios

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden", "projection_sprint4.json")


def _serialize_result(plan, simulation_result) -> dict:
    yearly_projections = [
        {
            "year": projection.year,
            "age_self": projection.age_self,
            "gross_income": int(projection.gross_income.amount),
            "pension_income": int(projection.pension_income.amount),
            "income_tax": int(projection.income_tax.amount),
            "resident_tax": int(projection.resident_tax.amount),
            "social_insurance": int(projection.social_insurance.amount),
            "net_income": int(projection.net_income.amount),
            "total_expense": int(projection.total_expense.amount),
            "net_cashflow": int(projection.net_cashflow.amount),
            "account_balances": {
                account_id: int(balance.amount) for account_id, balance in projection.account_balances.items()
            },
            "networth": int(projection.networth.amount),
        }
        for projection in simulation_result.yearly_projections
    ]
    milestone_outcomes = [
        {"milestone_id": outcome.milestone_id, "achieved": outcome.achieved, "achieved_year": outcome.achieved_year}
        for outcome in simulation_result.milestone_outcomes
    ]
    return {
        "config_version": "sprint8-tax_2026_portfolio_2026_pension_2026",
        "yearly_projections": yearly_projections,
        "milestone_outcomes": milestone_outcomes,
        "networth_chart": build_networth_chart(plan, simulation_result),
    }


class ProjectionRegressionTest(unittest.TestCase):
    def test_fixed_scenario_matches_golden_baseline(self) -> None:
        plan = build_scenario_plan()
        portfolios = build_scenario_portfolios()
        tax_rules = load_tax_rules()
        portfolio_rules = load_portfolio_rules()
        pension_rules = load_pension_rules()
        result = run_projection(plan, portfolios, tax_rules, portfolio_rules, pension_rules)
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
