import os
import unittest

from adapters.sheets.sheets_input_adapter import DEFAULT_CREDENTIALS_PATH, load_plan, load_portfolios, load_scenarios
from core.domain.account import AccountType
from core.domain.plan import Plan
from core.domain.user import Prefecture

SAMPLE_ACCOUNT_IDS = {"acc_cash_001", "acc_nisa_growth_001", "acc_ideco_001"}


@unittest.skipUnless(
    os.path.exists(DEFAULT_CREDENTIALS_PATH),
    "Google Sheets認証キー(secrets/gsheets_credentials.json)がないためスキップ",
)
class SheetsInputAdapterIntegrationTest(unittest.TestCase):
    def test_build_plan_from_test_spreadsheet(self) -> None:
        plan = load_plan()

        self.assertIsInstance(plan, Plan)
        self.assertEqual(plan.plan_id, "plan_001")
        self.assertEqual(plan.user.residence, Prefecture.TOKYO)

        self.assertEqual({a.account_id for a in plan.accounts}, SAMPLE_ACCOUNT_IDS)
        nisa_account = next(a for a in plan.accounts if a.account_id == "acc_nisa_growth_001")
        self.assertEqual(nisa_account.account_type, AccountType.NISA_GROWTH)
        self.assertEqual(nisa_account.monthly_contribution.amount, 50_000)

        self.assertEqual(len(plan.incomes), 1)
        self.assertEqual(plan.incomes[0].source, "salary")
        self.assertEqual(plan.incomes[0].end_condition.age, 60)

        self.assertEqual(len(plan.expenses), 1)
        self.assertEqual(plan.expenses[0].category, "living")
        self.assertFalse(plan.expenses[0].is_flexible)

    def test_load_portfolios_are_keyed_by_account_id(self) -> None:
        portfolios = load_portfolios()

        self.assertEqual(set(portfolios.keys()), SAMPLE_ACCOUNT_IDS)
        self.assertEqual(portfolios["acc_nisa_growth_001"].holdings[0].cost_basis.amount, 3_000_000)

    def test_load_scenarios_from_test_spreadsheet(self) -> None:
        plan = load_plan()
        scenarios = load_scenarios(plan.plan_id)

        self.assertEqual({s.scenario_id for s in scenarios}, {"scenario_60", "scenario_65"})
        scenario_60 = next(s for s in scenarios if s.scenario_id == "scenario_60")
        self.assertEqual(scenario_60.overrides["retirement_age"], 60)


if __name__ == "__main__":
    unittest.main()
