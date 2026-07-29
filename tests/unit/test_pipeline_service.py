import unittest
from datetime import date

from core.domain.account import Account, AccountType
from core.domain.asset import Asset
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.milestone import Milestone, MilestoneType
from core.domain.pension import ClaimTiming, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.services.pipeline_service import run_pipeline_for_plan
from tests.portfolio_test_fixtures import no_allocation_contribution_strategy


def _minimal_plan(**overrides) -> Plan:
    user = User(birth_date=date(1990, 4, 1))
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(age=65),
    )
    defaults = dict(
        plan_id="plan_test",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.zero()),
        accounts=[Account(account_id="acc_1", account_type=AccountType.TAXABLE)],
        tax_config=TaxConfig(),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH, AccountType.TAXABLE]),
        contribution_strategy=no_allocation_contribution_strategy(),
        incomes=[
            Income(
                income_id="income_1",
                source="salary",
                amount=Money.of(3_000_000),
                growth_rate=Rate.zero(),
                start_condition=EventCondition.plan_start(),
            )
        ],
    )
    defaults.update(overrides)
    return Plan(**defaults)


def _portfolios_for(plan: Plan, balance: int = 1_000_000) -> dict[str, Portfolio]:
    asset = Asset(asset_class="equity_sp500", expected_return=Rate.zero())
    holding = Holding(asset=asset, quantity=1, current_value=Money.of(balance), cost_basis=Money.of(balance))
    return {account.account_id: Portfolio(holdings=[holding]) for account in plan.accounts}


class RunPipelineForPlanTest(unittest.TestCase):
    def test_returns_full_outcome_when_montecarlo_and_historical_are_skipped(self) -> None:
        plan = _minimal_plan()
        portfolios = _portfolios_for(plan)

        outcome = run_pipeline_for_plan(
            plan, portfolios, Money.of(5_000_000), skip_montecarlo=True, skip_historical=True
        )

        self.assertTrue(outcome.succeeded)
        self.assertEqual(outcome.semantic_errors, [])
        self.assertIsNotNone(outcome.result)
        self.assertTrue(len(outcome.result.yearly_projections) > 0)
        self.assertIsNotNone(outcome.dashboard)
        self.assertEqual(outcome.dashboard["target_ending_networth"], Money.of(5_000_000))
        self.assertIsNotNone(outcome.sensitivity_result)
        self.assertIsNone(outcome.montecarlo_result)
        self.assertIsNone(outcome.montecarlo_reference_1971_result)
        self.assertIsNone(outcome.historical_result)

    def test_semantic_error_short_circuits_before_running_projection(self) -> None:
        # 退職年齢が現在年齢より若いマイルストーンは意味的エラー（validate_plan）で弾かれる
        plan = _minimal_plan(
            milestones=[
                Milestone(
                    milestone_id="m1",
                    milestone_type=MilestoneType.RETIREMENT,
                    trigger=EventCondition.at_age(10),
                )
            ]
        )
        portfolios = _portfolios_for(plan)

        outcome = run_pipeline_for_plan(
            plan, portfolios, Money.zero(), skip_montecarlo=True, skip_historical=True
        )

        self.assertFalse(outcome.succeeded)
        self.assertTrue(len(outcome.semantic_errors) > 0)
        self.assertIsNone(outcome.result)
        self.assertIsNone(outcome.dashboard)
        self.assertIsNone(outcome.sensitivity_result)

    def test_input_warnings_are_passed_through_unchanged(self) -> None:
        plan = _minimal_plan()
        portfolios = _portfolios_for(plan)
        warnings = [object()]

        outcome = run_pipeline_for_plan(
            plan, portfolios, Money.zero(), input_warnings=warnings, skip_montecarlo=True, skip_historical=True
        )

        self.assertIs(outcome.input_warnings, warnings)

    def test_progress_callback_is_invoked_for_each_phase(self) -> None:
        plan = _minimal_plan()
        portfolios = _portfolios_for(plan)
        messages: list[str] = []

        run_pipeline_for_plan(
            plan, portfolios, Money.zero(), skip_montecarlo=True, skip_historical=True, progress=messages.append
        )

        self.assertTrue(len(messages) >= 3)
        self.assertTrue(any("検証" in m for m in messages))


if __name__ == "__main__":
    unittest.main()
