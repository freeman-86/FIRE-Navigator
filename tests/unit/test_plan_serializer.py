import unittest
from datetime import date

from adapters.local.plan_serializer import to_json_dict
from core.domain.account import Account, AccountType
from core.domain.allocation import AllocationPolicy, AllocationTarget
from core.domain.asset import Asset
from core.domain.child import Child
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.education_expense import EducationExpenseBand
from core.domain.expense import Expense
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.one_time_expense import OneTimeExpense
from core.domain.pension import ClaimTiming, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy


def _minimal_plan(**overrides) -> Plan:
    user = User(birth_date=date(1990, 4, 1))
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.of(780_000)),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(age=65),
    )
    defaults = dict(
        plan_id="plan_001",
        name="ベースプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.TODAY),
        assumptions=Assumptions(inflation_rate=Rate.of("0.02")),
        accounts=[],
        tax_config=TaxConfig(),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
        contribution_strategy=ContributionStrategy(order=[AccountType.CASH]),
    )
    defaults.update(overrides)
    return Plan(**defaults)


class ToJsonDictTest(unittest.TestCase):
    def test_serializes_master_fields(self) -> None:
        plan = _minimal_plan()

        data = to_json_dict(plan, {}, Money.of(20_000_000))

        self.assertEqual(data["plan_id"], "plan_001")
        self.assertEqual(data["name"], "ベースプラン")
        self.assertEqual(data["user"], {"birth_date": "1990-04-01"})
        self.assertEqual(data["assumptions"], {"inflation_rate": "0.02"})
        self.assertEqual(
            data["pension"],
            {"national_pension_estimate_annual": 780000, "employee_pension_estimate_annual": 0, "claim_age": 65},
        )
        self.assertEqual(data["target_ending_networth"], 20000000)

    def test_serializes_account_with_matching_portfolio_holding(self) -> None:
        account = Account(account_id="acc_1", account_type=AccountType.TAXABLE, monthly_contribution=Money.of(30_000))
        holding = Holding(
            asset=Asset(asset_class="equity_sp500", expected_return=Rate.of("0.05")),
            quantity=1,
            current_value=Money.of(2_000_000),
            cost_basis=Money.of(1_500_000),
        )
        portfolios = {"acc_1": Portfolio(holdings=[holding])}
        plan = _minimal_plan(accounts=[account])

        data = to_json_dict(plan, portfolios, Money.zero())

        self.assertEqual(
            data["accounts"],
            [
                {
                    "account_id": "acc_1",
                    "account_type": "taxable",
                    "monthly_contribution": 30000,
                    "asset_class": "equity_sp500",
                    "expected_return": "0.05",
                    "current_value": 2000000,
                    "cost_basis": 1500000,
                }
            ],
        )

    def test_cost_basis_equal_to_current_value_serializes_as_null(self) -> None:
        # 取得原価=残高（含み益ゼロ）の場合はnullにして、読み込み側の「未入力→残高と同額」という
        # デフォルト解決ロジックと対称にする。
        account = Account(account_id="acc_1", account_type=AccountType.CASH)
        holding = Holding(
            asset=Asset(asset_class="cash", expected_return=Rate.zero()),
            quantity=1,
            current_value=Money.of(1_000_000),
            cost_basis=Money.of(1_000_000),
        )
        plan = _minimal_plan(accounts=[account])

        data = to_json_dict(plan, {"acc_1": Portfolio(holdings=[holding])}, Money.zero())

        self.assertIsNone(data["accounts"][0]["cost_basis"])

    def test_serializes_income_with_event_conditions(self) -> None:
        income = Income(
            income_id="income_1",
            source="salary",
            amount=Money.of(6_000_000),
            growth_rate=Rate.of("0.01"),
            start_condition=EventCondition.plan_start(),
            end_condition=EventCondition.at_age(60),
        )
        plan = _minimal_plan(incomes=[income])

        data = to_json_dict(plan, {}, Money.zero())

        self.assertEqual(
            data["incomes"],
            [
                {
                    "income_id": "income_1",
                    "source": "salary",
                    "amount": 6000000,
                    "growth_rate": "0.01",
                    "start_condition": {"type": "plan_start"},
                    "end_condition": {"type": "age", "age": 60},
                }
            ],
        )

    def test_serializes_recurring_and_one_time_expenses_into_one_list_with_kind(self) -> None:
        recurring = Expense(
            expense_id="expense_living",
            category="living",
            amount=Money.of(3_600_000),
            growth_rate=Rate.of("0.02"),
        )
        one_time = OneTimeExpense(
            expense_id="expense_car",
            category="車",
            amount=Money.of(3_000_000),
            trigger=EventCondition.at_age(45),
        )
        plan = _minimal_plan(expenses=[recurring], one_time_expenses=[one_time])

        data = to_json_dict(plan, {}, Money.zero())

        self.assertEqual(len(data["expenses"]), 2)
        self.assertEqual(data["expenses"][0]["kind"], "recurring")
        self.assertNotIn("trigger", data["expenses"][0])
        self.assertEqual(data["expenses"][1]["kind"], "one_time")
        self.assertEqual(data["expenses"][1]["trigger"], {"type": "age", "age": 45})
        self.assertNotIn("growth_rate", data["expenses"][1])

    def test_serializes_allocation_policy(self) -> None:
        policy = AllocationPolicy(targets=[AllocationTarget(age=30, weights={"equity_sp500": Rate.of("0.8")})])
        plan = _minimal_plan(allocation_policy=policy)

        data = to_json_dict(plan, {}, Money.zero())

        self.assertEqual(data["allocation_policy"], {"targets": [{"age": 30, "weights": {"equity_sp500": "0.8"}}]})

    def test_none_allocation_policy_serializes_as_null(self) -> None:
        plan = _minimal_plan(allocation_policy=None)

        data = to_json_dict(plan, {}, Money.zero())

        self.assertIsNone(data["allocation_policy"])

    def test_serializes_children_and_education_expenses(self) -> None:
        child = Child(child_id="child_001", birth_date=date(2022, 4, 1))
        band = EducationExpenseBand(
            band_id="band_1", child_id="child_001", category="小学校", start_age=6, end_age=11,
            monthly_amount=Money.of(20_000),
        )
        plan = _minimal_plan(children=[child], education_expenses=[band])

        data = to_json_dict(plan, {}, Money.zero())

        self.assertEqual(data["children"], [{"child_id": "child_001", "birth_date": "2022-04-01"}])
        self.assertEqual(
            data["education_expenses"],
            [{"band_id": "band_1", "child_id": "child_001", "category": "小学校", "start_age": 6, "end_age": 11, "monthly_amount": 20000}],
        )


if __name__ == "__main__":
    unittest.main()
