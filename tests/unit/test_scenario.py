import unittest
from datetime import date

from core.domain.account import AccountType
from core.domain.milestone import Milestone, MilestoneType
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.scenario import Scenario, apply_scenario
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from tests.portfolio_test_fixtures import no_allocation_contribution_strategy


def _base_plan(milestones=None) -> Plan:
    user = User(birth_date=date(1990, 4, 1))
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )
    return Plan(
        plan_id="plan_001",
        name="ベースプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.TODAY),
        assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.zero()),
        accounts=[],
        tax_config=TaxConfig(),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
        contribution_strategy=no_allocation_contribution_strategy(),
        milestones=milestones or [],
    )


class ApplyScenarioTest(unittest.TestCase):
    def test_retirement_age_override_adds_milestone(self) -> None:
        base_plan = _base_plan()
        scenario = Scenario(scenario_id="scenario_60", plan_id="plan_001", name="60歳退職", overrides={"retirement_age": 60})

        derived_plan = apply_scenario(base_plan, scenario)

        retirement_milestones = [m for m in derived_plan.milestones if m.milestone_type == MilestoneType.RETIREMENT]
        self.assertEqual(len(retirement_milestones), 1)
        self.assertEqual(retirement_milestones[0].trigger.age, 60)

    def test_retirement_age_override_replaces_existing_milestone(self) -> None:
        existing = Milestone(
            milestone_id="milestone_retire_001",
            milestone_type=MilestoneType.RETIREMENT,
            trigger=EventCondition.at_age(65),
        )
        base_plan = _base_plan(milestones=[existing])
        scenario = Scenario(scenario_id="scenario_60", plan_id="plan_001", name="60歳退職", overrides={"retirement_age": 60})

        derived_plan = apply_scenario(base_plan, scenario)

        retirement_milestones = [m for m in derived_plan.milestones if m.milestone_type == MilestoneType.RETIREMENT]
        self.assertEqual(len(retirement_milestones), 1)
        self.assertEqual(retirement_milestones[0].trigger.age, 60)

    def test_base_plan_is_not_mutated(self) -> None:
        base_plan = _base_plan()
        scenario = Scenario(scenario_id="scenario_60", plan_id="plan_001", name="60歳退職", overrides={"retirement_age": 60})

        apply_scenario(base_plan, scenario)

        self.assertEqual(base_plan.milestones, [])

    def test_mismatched_plan_id_raises(self) -> None:
        base_plan = _base_plan()
        scenario = Scenario(scenario_id="scenario_60", plan_id="plan_999", name="60歳退職", overrides={"retirement_age": 60})

        with self.assertRaises(ValueError):
            apply_scenario(base_plan, scenario)

    def test_unsupported_override_key_raises(self) -> None:
        base_plan = _base_plan()
        scenario = Scenario(scenario_id="scenario_x", plan_id="plan_001", name="不明な上書き", overrides={"expense_multiplier": 1.2})

        with self.assertRaises(ValueError):
            apply_scenario(base_plan, scenario)


if __name__ == "__main__":
    unittest.main()
