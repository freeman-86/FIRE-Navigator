import unittest
from datetime import date

from core.domain.account import AccountType
from core.domain.milestone import Milestone, MilestoneType
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.simulation_result import YearlyProjection
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.simulation.projection.milestone_evaluation import evaluate_milestones
from tests.portfolio_test_fixtures import no_allocation_contribution_strategy


def _plan(milestones) -> Plan:
    user = User(birth_date=date(1990, 4, 1), residence=Prefecture.TOKYO)
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )
    return Plan(
        plan_id="plan_001",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.TODAY),
        assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.zero()),
        accounts=[],
        tax_config=TaxConfig(residence=Prefecture.TOKYO),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
        contribution_strategy=no_allocation_contribution_strategy(),
        milestones=milestones,
    )


def _projection(year: int, age: int, networth: int, total_expense: int = 3_000_000) -> YearlyProjection:
    return YearlyProjection(
        year=year,
        age_self=age,
        gross_income=Money.zero(),
        income_tax=Money.zero(),
        resident_tax=Money.zero(),
        social_insurance=Money.zero(),
        net_income=Money.zero(),
        total_expense=Money.of(total_expense),
        net_cashflow=Money.zero(),
        account_balances={},
        networth=Money.of(networth),
    )


class EvaluateMilestonesTest(unittest.TestCase):
    def test_age_based_milestone_achieved_within_horizon(self) -> None:
        milestone = Milestone(
            milestone_id="milestone_retire_001",
            milestone_type=MilestoneType.RETIREMENT,
            trigger=EventCondition.at_age(60),
        )
        plan = _plan([milestone])
        # birth_date=1990-04-01なので60歳になるのは2050年
        projections = [_projection(year, age, 0) for year, age in [(2049, 59), (2050, 60), (2051, 61)]]

        outcomes = evaluate_milestones(plan, projections)

        self.assertEqual(len(outcomes), 1)
        self.assertTrue(outcomes[0].achieved)
        self.assertEqual(outcomes[0].achieved_year, 2050)

    def test_age_based_milestone_not_achieved_outside_horizon(self) -> None:
        milestone = Milestone(
            milestone_id="milestone_retire_001",
            milestone_type=MilestoneType.RETIREMENT,
            trigger=EventCondition.at_age(90),
        )
        plan = _plan([milestone])
        projections = [_projection(2026, 36, 0), _projection(2027, 37, 0)]

        outcomes = evaluate_milestones(plan, projections)

        self.assertFalse(outcomes[0].achieved)
        self.assertIsNone(outcomes[0].achieved_year)

    def test_networth_multiple_of_expense_achieved_dynamically(self) -> None:
        milestone = Milestone(
            milestone_id="milestone_fi_001",
            milestone_type=MilestoneType.FINANCIAL_INDEPENDENCE,
            trigger=EventCondition.networth_multiple_of_expense(25),
        )
        plan = _plan([milestone])
        projections = [
            _projection(2026, 36, networth=50_000_000, total_expense=3_000_000),  # 50M < 75M(25倍) 未達成
            _projection(2027, 37, networth=76_000_000, total_expense=3_000_000),  # 76M >= 75M 達成
        ]

        outcomes = evaluate_milestones(plan, projections)

        self.assertTrue(outcomes[0].achieved)
        self.assertEqual(outcomes[0].achieved_year, 2027)

    def test_networth_multiple_of_expense_never_achieved(self) -> None:
        milestone = Milestone(
            milestone_id="milestone_fi_001",
            milestone_type=MilestoneType.FINANCIAL_INDEPENDENCE,
            trigger=EventCondition.networth_multiple_of_expense(25),
        )
        plan = _plan([milestone])
        projections = [_projection(2026, 36, networth=1_000_000, total_expense=3_000_000)]

        outcomes = evaluate_milestones(plan, projections)

        self.assertFalse(outcomes[0].achieved)
        self.assertIsNone(outcomes[0].achieved_year)

    def test_no_milestones_returns_empty_list(self) -> None:
        plan = _plan([])
        outcomes = evaluate_milestones(plan, [_projection(2026, 36, 0)])
        self.assertEqual(outcomes, [])


if __name__ == "__main__":
    unittest.main()
