import unittest
from datetime import date

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset, AssetClass
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.milestone import Milestone, MilestoneType
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from tests.portfolio_test_fixtures import no_allocation_contribution_strategy


def _build_plan() -> Plan:
    user = User(birth_date=date(1990, 4, 1), residence=Prefecture.TOKYO)

    asset = Asset(
        asset_class=AssetClass.GLOBAL_EQUITY,
        expected_return=Rate.from_percent(5),
        volatility=Rate.from_percent(15),
    )
    holding = Holding(asset=asset, quantity=100, cost_basis=Money.of(300_000))
    account = Account(
        account_id="acc_nisa_growth_001",
        account_type=AccountType.NISA_GROWTH,
        owner=OwnerType.SELF,
        portfolio=Portfolio(holdings=[holding]),
    )

    income = Income(
        income_id="income_salary_001",
        source="salary",
        amount=Money.of(6_000_000),
        growth_rate=Rate.from_percent(1),
        start_condition=EventCondition.plan_start(),
        end_condition=EventCondition.at_age(60),
    )

    milestone = Milestone(
        milestone_id="milestone_fi_001",
        milestone_type=MilestoneType.FINANCIAL_INDEPENDENCE,
        trigger=EventCondition.networth_multiple_of_expense(25),
    )

    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.of(780_000)),
        employee_pension=PensionEntitlement(estimate_annual=Money.of(1_200_000)),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )

    return Plan(
        plan_id="plan_001",
        name="ベースプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.TODAY),
        assumptions=Assumptions(
            inflation_rate=Rate.from_percent(2),
            investment_growth_rate=Rate.from_percent(5),
        ),
        accounts=[account],
        tax_config=TaxConfig(residence=Prefecture.TOKYO),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(
            order=[AccountType.CASH, AccountType.TAXABLE, AccountType.NISA_GROWTH, AccountType.IDECO]
        ),
        contribution_strategy=no_allocation_contribution_strategy(),
        incomes=[income],
        milestones=[milestone],
    )


class PlanTest(unittest.TestCase):
    def test_plan_assembles_nested_entities(self) -> None:
        plan = _build_plan()

        self.assertEqual(plan.accounts[0].portfolio.holdings[0].asset.asset_class, AssetClass.GLOBAL_EQUITY)
        self.assertEqual(plan.incomes[0].amount, Money.of(6_000_000))
        self.assertEqual(plan.milestones[0].trigger.multiple, 25)
        self.assertEqual(plan.withdrawal_strategy.order[0], AccountType.CASH)

    def test_user_age_at_plan_start(self) -> None:
        plan = _build_plan()
        age = plan.user.age_at(date(2026, 7, 18))
        self.assertEqual(age.years, 36)


if __name__ == "__main__":
    unittest.main()
