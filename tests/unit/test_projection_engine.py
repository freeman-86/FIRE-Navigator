import unittest
from datetime import date

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset, AssetClass
from core.domain.contribution_strategy import ContributionStrategy
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
from repositories.config_repository import load_portfolio_rules, load_tax_rules
from tests.portfolio_test_fixtures import empty_portfolio_rules, no_allocation_contribution_strategy
from tests.tax_test_fixtures import zero_tax_rules


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
        contribution_strategy=no_allocation_contribution_strategy(),
    )
    defaults.update(overrides)
    return Plan(**defaults)


def _portfolio(balance: int, asset_class: AssetClass = AssetClass.GLOBAL_EQUITY) -> Portfolio:
    asset = Asset(asset_class=asset_class, expected_return=Rate.from_percent(5), volatility=Rate.from_percent(15))
    holding = Holding(asset=asset, quantity=1, cost_basis=Money.of(balance))
    return Portfolio(holdings=[holding])


class ProjectionEngineTest(unittest.TestCase):
    def test_default_horizon_is_30_years_without_retirement_milestone(self) -> None:
        plan = _minimal_plan()
        result = run_projection(plan, {}, zero_tax_rules(), empty_portfolio_rules())

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
        result = run_projection(plan, {}, zero_tax_rules(), empty_portfolio_rules())

        # 1990年生まれが60歳になるのは2050年
        self.assertEqual(result.yearly_projections[-1].year, 2050)
        self.assertEqual(result.yearly_projections[-1].age_self, 60)

    def test_surplus_and_growth_compound_networth(self) -> None:
        account = Account(account_id="acc_001", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
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
        portfolios = {"acc_001": _portfolio(1_000_000)}

        result = run_projection(plan, portfolios, zero_tax_rules(), empty_portfolio_rules())
        first_year = result.yearly_projections[0]

        self.assertEqual(first_year.gross_income, Money.of(5_000_000))
        self.assertEqual(first_year.total_expense, Money.of(3_000_000))
        self.assertEqual(first_year.net_cashflow, Money.of(2_000_000))
        # 口座残高: 1,000,000 * 1.05 = 1,050,000 / 余剰: 0 * 1.05 + 2,000,000 = 2,000,000
        self.assertEqual(first_year.account_balances["acc_001"], Money.of(1_050_000))
        self.assertEqual(first_year.account_balances["unallocated_surplus"], Money.of(2_000_000))
        self.assertEqual(first_year.networth, Money.of(3_050_000))

    def test_account_without_portfolio_entry_starts_at_zero_balance(self) -> None:
        account = Account(account_id="acc_no_portfolio", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        plan = _minimal_plan(accounts=[account])

        result = run_projection(plan, {}, zero_tax_rules(), empty_portfolio_rules())

        self.assertEqual(result.yearly_projections[0].account_balances["acc_no_portfolio"], Money.zero())

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
        result = run_projection(plan, {}, zero_tax_rules(), empty_portfolio_rules())

        by_age = {p.age_self: p.gross_income for p in result.yearly_projections}
        self.assertEqual(by_age[59], Money.of(1_000_000))
        self.assertEqual(by_age[60], Money.zero())
        self.assertEqual(by_age[62], Money.zero())


class NisaIdecoComparisonTest(unittest.TestCase):
    """Sprint6の終了条件：NISA・iDeCoを使った場合と使わない場合で、税引後資産推移がどれだけ変わるかを比較できる。"""

    def _accounts_and_portfolios(self, with_ideco: bool):
        taxable = Account(account_id="acc_taxable", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        portfolios = {"acc_taxable": _portfolio(1_000_000)}
        accounts = [taxable]
        if with_ideco:
            ideco = Account(
                account_id="acc_ideco",
                account_type=AccountType.IDECO,
                owner=OwnerType.SELF,
                monthly_contribution=Money.of(23_000),
            )
            accounts.append(ideco)
            portfolios["acc_ideco"] = _portfolio(0, AssetClass.DOMESTIC_BOND)
        return accounts, portfolios

    def _income(self) -> Income:
        return Income(
            income_id="income_001",
            source="salary",
            amount=Money.of(6_000_000),
            growth_rate=Rate.zero(),
            start_condition=EventCondition.plan_start(),
        )

    def _expense(self) -> Expense:
        return Expense(
            expense_id="expense_001",
            category="living",
            amount=Money.of(3_000_000),
            growth_rate=Rate.zero(),
        )

    def test_using_ideco_produces_higher_after_tax_networth_than_not_using_it(self) -> None:
        tax_rules = load_tax_rules()
        portfolio_rules = load_portfolio_rules()

        accounts_with, portfolios_with = self._accounts_and_portfolios(with_ideco=True)
        accounts_without, portfolios_without = self._accounts_and_portfolios(with_ideco=False)

        with_ideco = _minimal_plan(
            accounts=accounts_with,
            incomes=[self._income()],
            expenses=[self._expense()],
            assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.from_percent(5)),
            contribution_strategy=ContributionStrategy(order=[AccountType.TAXABLE]),
        )
        without_ideco = _minimal_plan(
            accounts=accounts_without,
            incomes=[self._income()],
            expenses=[self._expense()],
            assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.from_percent(5)),
            contribution_strategy=ContributionStrategy(order=[AccountType.TAXABLE]),
        )

        result_with_ideco = run_projection(with_ideco, portfolios_with, tax_rules, portfolio_rules)
        result_without_ideco = run_projection(without_ideco, portfolios_without, tax_rules, portfolio_rules)

        # iDeCo拠出は所得控除の対象になり手取りが増えるため、同じ収入・支出でもiDeCoを使った方が
        # 税引後ネットワースが大きくなる。
        first_year_with = result_with_ideco.yearly_projections[0]
        first_year_without = result_without_ideco.yearly_projections[0]
        self.assertGreater(first_year_with.net_income, first_year_without.net_income)
        self.assertGreater(first_year_with.networth, first_year_without.networth)

        final_with = result_with_ideco.yearly_projections[-1]
        final_without = result_without_ideco.yearly_projections[-1]
        self.assertGreater(final_with.networth, final_without.networth)


if __name__ == "__main__":
    unittest.main()
