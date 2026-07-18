import unittest
from datetime import date

from core.domain.account import AccountType
from core.domain.errors import ConfigInconsistencyError, SemanticValidationError
from core.domain.milestone import Milestone, MilestoneType
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement, PensionRules
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.services.validation_service import validate_plan
from tests.portfolio_test_fixtures import no_allocation_contribution_strategy


def _plan(milestones=None, spouse=None, claim_age: int = 65) -> Plan:
    user = User(birth_date=date(1990, 4, 1), residence=Prefecture.TOKYO, spouse=spouse)
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=claim_age),
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
        milestones=milestones or [],
    )


def _pension_rules() -> PensionRules:
    return PensionRules(
        standard_claim_age=65,
        earliest_claim_age=60,
        latest_claim_age=75,
        early_reduction_rate_per_month=Rate.of("0.004"),
        deferred_increase_rate_per_month=Rate.of("0.007"),
    )


class ValidateRetirementAgeTest(unittest.TestCase):
    def test_retirement_age_younger_than_current_age_is_flagged(self) -> None:
        # 1990年生まれ、reference_date=2026年 -> 現在36歳。退職年齢30歳は矛盾。
        milestone = Milestone(
            milestone_id="m1", milestone_type=MilestoneType.RETIREMENT, trigger=EventCondition.at_age(30)
        )
        plan = _plan(milestones=[milestone])

        errors = validate_plan(plan, reference_date=date(2026, 7, 18))

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], SemanticValidationError)
        self.assertEqual(errors[0].field_path, "milestones[m1].trigger.age")

    def test_valid_retirement_age_is_not_flagged(self) -> None:
        milestone = Milestone(
            milestone_id="m1", milestone_type=MilestoneType.RETIREMENT, trigger=EventCondition.at_age(65)
        )
        plan = _plan(milestones=[milestone])

        errors = validate_plan(plan, reference_date=date(2026, 7, 18))
        self.assertEqual(errors, [])


class ValidateSpouseBirthDateTest(unittest.TestCase):
    def test_future_spouse_birth_date_is_flagged(self) -> None:
        spouse = User(birth_date=date(2099, 1, 1), residence=Prefecture.TOKYO)
        plan = _plan(spouse=spouse)

        errors = validate_plan(plan, reference_date=date(2026, 7, 18))

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].field_path, "user.spouse.birth_date")


class ValidatePensionClaimAgeTest(unittest.TestCase):
    def test_claim_age_outside_allowed_range_is_flagged(self) -> None:
        plan = _plan(claim_age=50)

        errors = validate_plan(plan, pension_rules=_pension_rules(), reference_date=date(2026, 7, 18))

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ConfigInconsistencyError)
        self.assertEqual(errors[0].field_path, "pension.claim_timing.age")

    def test_claim_age_within_range_is_not_flagged(self) -> None:
        plan = _plan(claim_age=65)
        errors = validate_plan(plan, pension_rules=_pension_rules(), reference_date=date(2026, 7, 18))
        self.assertEqual(errors, [])

    def test_no_pension_rules_skips_check(self) -> None:
        plan = _plan(claim_age=999)
        errors = validate_plan(plan, pension_rules=None, reference_date=date(2026, 7, 18))
        self.assertEqual(errors, [])


class ValidateMilestoneMultipleTest(unittest.TestCase):
    def test_non_positive_multiple_is_flagged(self) -> None:
        milestone = Milestone(
            milestone_id="m_fi",
            milestone_type=MilestoneType.FINANCIAL_INDEPENDENCE,
            trigger=EventCondition.networth_multiple_of_expense(-5),
        )
        plan = _plan(milestones=[milestone])

        errors = validate_plan(plan, reference_date=date(2026, 7, 18))

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].field_path, "milestones[m_fi].trigger.multiple")


if __name__ == "__main__":
    unittest.main()
