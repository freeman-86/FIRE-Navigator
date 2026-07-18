import unittest
from datetime import date
from decimal import Decimal

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset, AssetClass
from core.domain.expense import Expense
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
from core.simulation.projection.projection_engine import run_projection


def _minimal_plan(**overrides) -> Plan:
    user = User(birth_date=date(1990, 4, 1), residence=Prefecture.TOKYO)
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )
    defaults = dict(
        plan_id="plan_test",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.zero()),
        accounts=[],
        tax_config=TaxConfig(residence=Prefecture.TOKYO),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
    )
    defaults.update(overrides)
    return Plan(**defaults)


class ProjectionEngineTest(unittest.TestCase):
    def test_default_horizon_is_30_years_without_retirement_milestone(self) -> None:
        plan = _minimal_plan()
        result = run_projection(plan)

        self.assertEqual(len(result.yearly_projections), 30)
        self.assertEqual(result.yearly_projections[0].year, 2026)
        self.assertEqual(result.yearly_projections[-1].year, 2055)

    def test_horizon_stops_at_retirement_milestone_age(self) -> None:
        plan = _minimal_plan(
            milestones=[
                Milestone(
                    milestone_id="milestone_retire_001",
                    milestone_type=MilestoneType.RETIREMENT,
                    trigger=EventCondition.at_age(60),
                )
            ]
        )
        result = run_projection(plan)

        # 1990年生まれが60歳になるのは2050年
        self.assertEqual(result.yearly_projections[-1].year, 2050)
        self.assertEqual(result.yearly_projections[-1].age_self, 60)

    def test_surplus_and_growth_compound_networth(self) -> None:
        asset = Asset(
            asset_class=AssetClass.GLOBAL_EQUITY,
            expected_return=Rate.from_percent(5),
            volatility=Rate.from_percent(15),
        )
        holding = Holding(asset=asset, quantity=1, cost_basis=Money.of(1_000_000))
        account = Account(
            account_id="acc_001",
            account_type=AccountType.TAXABLE,
            owner=OwnerType.SELF,
            portfolio=Portfolio(holdings=[holding]),
        )
        income = Income(
            income_id="income_001",
            source="salary",
            amount=Money.of(5_000_000),
            growth_rate=Rate.zero(),
            start_condition=EventCondition.plan_start(),
        )
        expense = Expense(
            expense_id="expense_001",
            category="living",
            amount=Money.of(3_000_000),
            growth_rate=Rate.zero(),
        )
        plan = _minimal_plan(
            accounts=[account],
            incomes=[income],
            expenses=[expense],
            assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.from_percent(5)),
        )

        result = run_projection(plan)
        first_year = result.yearly_projections[0]

        self.assertEqual(first_year.gross_income, Money.of(5_000_000))
        self.assertEqual(first_year.total_expense, Money.of(3_000_000))
        self.assertEqual(first_year.net_cashflow, Money.of(2_000_000))
        # 口座残高: 1,000,000 * 1.05 = 1,050,000 / 余剰: 0 * 1.05 + 2,000,000 = 2,000,000
        self.assertEqual(first_year.account_balances["acc_001"], Money.of(1_050_000))
        self.assertEqual(first_year.account_balances["unallocated_surplus"], Money.of(2_000_000))
        self.assertEqual(first_year.networth, Money.of(3_050_000))

    def test_income_stops_at_end_condition_age(self) -> None:
        income = Income(
            income_id="income_001",
            source="salary",
            amount=Money.of(1_000_000),
            growth_rate=Rate.zero(),
            start_condition=EventCondition.plan_start(),
            end_condition=EventCondition.at_age(60),
        )
        plan = _minimal_plan(
            incomes=[income],
            milestones=[
                Milestone(
                    milestone_id="milestone_retire_001",
                    milestone_type=MilestoneType.RETIREMENT,
                    trigger=EventCondition.at_age(62),
                )
            ],
        )
        result = run_projection(plan)

        by_age = {p.age_self: p.gross_income for p in result.yearly_projections}
        self.assertEqual(by_age[59], Money.of(1_000_000))
        self.assertEqual(by_age[60], Money.zero())
        self.assertEqual(by_age[62], Money.zero())


if __name__ == "__main__":
    unittest.main()
