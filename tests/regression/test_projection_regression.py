import json
import os
import unittest

from core.simulation.projection.projection_engine import run_projection
from repositories.config_repository import load_pension_rules, load_portfolio_rules, load_tax_rules
from reports.chart_builder import build_networth_chart
from tests.regression import (
    scenario_account_exhaustion,
    scenario_no_retirement,
    scenario_spouse_deduction,
    scenario_sprint4,
)

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")

# (golden filename, plan builder, portfolios builder)
SCENARIOS = (
    ("projection_sprint4.json", scenario_sprint4.build_scenario_plan, scenario_sprint4.build_scenario_portfolios),
    (
        "projection_spouse_deduction.json",
        scenario_spouse_deduction.build_plan,
        scenario_spouse_deduction.build_portfolios,
    ),
    ("projection_no_retirement.json", scenario_no_retirement.build_plan, scenario_no_retirement.build_portfolios),
    (
        "projection_account_exhaustion.json",
        scenario_account_exhaustion.build_plan,
        scenario_account_exhaustion.build_portfolios,
    ),
)


def serialize_result(plan, simulation_result) -> dict:
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
            "capital_gains_tax": int(projection.capital_gains_tax.amount),
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
        "config_version": "sprint13-capital_gains_tax_2026_portfolio_2026_pension_2026",
        "yearly_projections": yearly_projections,
        "milestone_outcomes": milestone_outcomes,
        "networth_chart": build_networth_chart(plan, simulation_result),
    }


# 後方互換: 以前このモジュールを直接importしていたコード向けのエイリアス
_serialize_result = serialize_result


class ProjectionRegressionTest(unittest.TestCase):
    def test_all_scenarios_match_golden_baseline(self) -> None:
        tax_rules = load_tax_rules()
        portfolio_rules = load_portfolio_rules()
        pension_rules = load_pension_rules()

        for golden_filename, build_plan, build_portfolios in SCENARIOS:
            with self.subTest(scenario=golden_filename):
                plan = build_plan()
                portfolios = build_portfolios()
                result = run_projection(plan, portfolios, tax_rules, portfolio_rules, pension_rules)
                actual = serialize_result(plan, result)

                golden_path = os.path.join(GOLDEN_DIR, golden_filename)
                with open(golden_path, encoding="utf-8") as f:
                    expected = json.load(f)

                self.assertEqual(
                    actual,
                    expected,
                    f"{golden_filename} の計算結果が一致しません。"
                    "意図した変更であればレビューを経てgolden fileを更新してください。",
                )


if __name__ == "__main__":
    unittest.main()
