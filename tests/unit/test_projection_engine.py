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
from core.simulation.projection.projection_engine import DEFAULT_LIFE_EXPECTANCY_AGE, run_projection
from core.simulation.withdrawal.withdrawal_engine import withdraw_shortfall
from repositories.config_repository import load_pension_rules, load_portfolio_rules, load_tax_rules
from tests.pension_test_fixtures import zero_pension_rules
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


def _portfolio(balance: int, asset_class: AssetClass = "equity_sp500") -> Portfolio:
    asset = Asset(asset_class=asset_class, expected_return=Rate.from_percent(5), volatility=Rate.from_percent(15))
    holding = Holding(asset=asset, quantity=1, cost_basis=Money.of(balance))
    return Portfolio(holdings=[holding])


def _run(plan: Plan, portfolios: dict[str, Portfolio] = None):
    return run_projection(plan, portfolios or {}, zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules())


class ProjectionEngineTest(unittest.TestCase):
    def test_default_horizon_is_30_years_without_retirement_milestone(self) -> None:
        plan = _minimal_plan()
        result = _run(plan)

        self.assertEqual(len(result.yearly_projections), 30)
        self.assertEqual(result.yearly_projections[0].year, 2026)
        self.assertEqual(result.yearly_projections[-1].year, 2055)

    def test_horizon_extends_to_life_expectancy_when_retirement_milestone_present(self) -> None:
        plan = _minimal_plan(
            milestones=[
                Milestone(
                    milestone_id="milestone_retire_001",
                    milestone_type=MilestoneType.RETIREMENT,
                    trigger=EventCondition.at_age(60),
                )
            ]
        )
        result = _run(plan)

        # 1990年生まれがDEFAULT_LIFE_EXPECTANCY_AGE歳になる年まで、退職後も継続してシミュレーションする
        expected_last_year = 1990 + DEFAULT_LIFE_EXPECTANCY_AGE
        self.assertEqual(result.yearly_projections[-1].year, expected_last_year)
        self.assertEqual(result.yearly_projections[-1].age_self, DEFAULT_LIFE_EXPECTANCY_AGE)

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

        result = _run(plan, portfolios)
        first_year = result.yearly_projections[0]

        self.assertEqual(first_year.gross_income, Money.of(5_000_000))
        self.assertEqual(first_year.total_expense, Money.of(3_000_000))
        self.assertEqual(first_year.net_cashflow, Money.of(2_000_000))
        # 口座残高: 追加拠出なしの口座は月次複利でも年率複利と一致する: 1,000,000 * 1.05 = 1,050,000
        # 余剰: 毎月の余剰(2,000,000/12)がその都度その年の残り月数分だけ月次複利で増える
        # （Sprint12月次化により、年末に一括計上していた旧仕様より高くなる。ドルコスト平均的な効果）
        self.assertEqual(first_year.account_balances["acc_001"], Money.of(1_050_000))
        self.assertEqual(first_year.account_balances["unallocated_surplus"], Money.of(2_045_434))
        self.assertEqual(first_year.networth, Money.of(3_095_434))

    def test_account_without_portfolio_entry_starts_at_zero_balance(self) -> None:
        account = Account(account_id="acc_no_portfolio", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        plan = _minimal_plan(accounts=[account])

        result = _run(plan)

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
        plan = _minimal_plan(incomes=[income])
        result = _run(plan)

        by_age = {p.age_self: p.gross_income for p in result.yearly_projections}
        self.assertEqual(by_age[59], Money.of(1_000_000))
        self.assertEqual(by_age[60], Money.zero())


class PensionAndWithdrawalTest(unittest.TestCase):
    """Sprint8の終了条件：退職後フェーズを含めた資産推移が、年金受給・取り崩し順序を考慮して計算される。"""

    def test_pension_income_starts_at_claim_age(self) -> None:
        pension = Pension(
            national_pension=PensionEntitlement(estimate_annual=Money.of(780_000)),
            employee_pension=PensionEntitlement(estimate_annual=Money.of(1_200_000)),
            claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
        )
        milestone = Milestone(
            milestone_id="milestone_retire_001",
            milestone_type=MilestoneType.RETIREMENT,
            trigger=EventCondition.at_age(65),
        )
        plan = _minimal_plan(pension=pension, milestones=[milestone])

        result = _run(plan)

        by_age = {p.age_self: p.pension_income for p in result.yearly_projections}
        self.assertEqual(by_age[64], Money.zero())
        self.assertEqual(by_age[65], Money.of(1_980_000))

    def test_early_claim_reduces_pension_income(self) -> None:
        pension_rules = load_pension_rules()
        pension = Pension(
            national_pension=PensionEntitlement(estimate_annual=Money.of(780_000)),
            employee_pension=PensionEntitlement(estimate_annual=Money.of(1_200_000)),
            claim_timing=ClaimTiming(timing_type=ClaimTimingType.EARLY, age=60),
        )
        milestone = Milestone(
            milestone_id="milestone_retire_001",
            milestone_type=MilestoneType.RETIREMENT,
            trigger=EventCondition.at_age(60),
        )
        plan = _minimal_plan(pension=pension, milestones=[milestone])

        result = run_projection(plan, {}, zero_tax_rules(), empty_portfolio_rules(), pension_rules)

        # 60歳受給(標準65歳より60ヶ月早い) -> 60ヶ月×0.4%=24%減額 -> 1,980,000×0.76=1,504,800
        by_age = {p.age_self: p.pension_income for p in result.yearly_projections}
        self.assertEqual(by_age[60], Money.of(1_504_800))

    def test_withdrawal_covers_post_retirement_shortfall_from_account_balance(self) -> None:
        account = Account(account_id="acc_taxable", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        expense = Expense(
            expense_id="expense_001",
            category="living",
            amount=Money.of(3_000_000),
            growth_rate=Rate.zero(),
        )
        milestone = Milestone(
            milestone_id="milestone_retire_001",
            milestone_type=MilestoneType.RETIREMENT,
            trigger=EventCondition.at_age(60),
        )
        plan = _minimal_plan(
            accounts=[account],
            expenses=[expense],
            milestones=[milestone],
            withdrawal_strategy=WithdrawalStrategy(order=[AccountType.TAXABLE]),
        )
        portfolios = {"acc_taxable": _portfolio(10_000_000, "cash")}

        result = _run(plan, portfolios)
        first_year = result.yearly_projections[0]

        # 収入ゼロ・支出300万円・成長率0%の年、口座から300万円が取り崩される
        self.assertEqual(first_year.account_balances["acc_taxable"], Money.of(7_000_000))
        self.assertEqual(first_year.account_balances["unallocated_surplus"], Money.zero())

    def test_unmet_shortfall_after_accounts_exhausted_flows_to_unallocated_surplus(self) -> None:
        account = Account(account_id="acc_taxable", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        expense = Expense(
            expense_id="expense_001",
            category="living",
            amount=Money.of(3_000_000),
            growth_rate=Rate.zero(),
        )
        milestone = Milestone(
            milestone_id="milestone_retire_001",
            milestone_type=MilestoneType.RETIREMENT,
            trigger=EventCondition.at_age(60),
        )
        plan = _minimal_plan(
            accounts=[account],
            expenses=[expense],
            milestones=[milestone],
            withdrawal_strategy=WithdrawalStrategy(order=[AccountType.TAXABLE]),
        )
        portfolios = {"acc_taxable": _portfolio(1_000_000, "cash")}

        result = _run(plan, portfolios)
        first_year = result.yearly_projections[0]

        # 口座残高100万円しかないのに支出300万円 -> 100万円取り崩して枯渇、残り200万円はunallocated_surplusがマイナスに
        self.assertEqual(first_year.account_balances["acc_taxable"], Money.zero())
        self.assertEqual(first_year.account_balances["unallocated_surplus"], Money.of(-2_000_000))


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
            portfolios["acc_ideco"] = _portfolio(0, "bond_us_treasury")
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
        pension_rules = load_pension_rules()

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

        result_with_ideco = run_projection(with_ideco, portfolios_with, tax_rules, portfolio_rules, pension_rules)
        result_without_ideco = run_projection(
            without_ideco, portfolios_without, tax_rules, portfolio_rules, pension_rules
        )

        # iDeCo拠出は所得控除の対象になり手取りが増えるため、同じ収入・支出でもiDeCoを使った方が
        # 税引後ネットワースが大きくなる。
        first_year_with = result_with_ideco.yearly_projections[0]
        first_year_without = result_without_ideco.yearly_projections[0]
        self.assertGreater(first_year_with.net_income, first_year_without.net_income)
        self.assertGreater(first_year_with.networth, first_year_without.networth)

        final_with = result_with_ideco.yearly_projections[-1]
        final_without = result_without_ideco.yearly_projections[-1]
        self.assertGreater(final_with.networth, final_without.networth)


class MonthlyProjectionsTest(unittest.TestCase):
    def test_monthly_projections_have_12_entries_per_year(self) -> None:
        plan = _minimal_plan()
        result = _run(plan)

        self.assertEqual(len(result.monthly_projections), len(result.yearly_projections) * 12)

    def test_monthly_projections_are_labelled_in_order(self) -> None:
        plan = _minimal_plan()
        result = _run(plan)

        first_year = result.yearly_projections[0].year
        first_twelve = result.monthly_projections[:12]
        self.assertEqual([p.year for p in first_twelve], [first_year] * 12)
        self.assertEqual([p.month for p in first_twelve], list(range(1, 13)))

    def test_year_end_snapshot_matches_last_month_of_that_year(self) -> None:
        account = Account(account_id="acc_taxable", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        plan = _minimal_plan(
            accounts=[account],
            assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.from_percent(5)),
        )
        portfolios = {"acc_taxable": _portfolio(1_000_000)}

        result = _run(plan, portfolios)

        first_year = result.yearly_projections[0]
        last_month_of_first_year = result.monthly_projections[11]
        self.assertEqual(last_month_of_first_year.year, first_year.year)
        self.assertEqual(last_month_of_first_year.month, 12)
        self.assertEqual(last_month_of_first_year.account_balances, first_year.account_balances)
        self.assertEqual(last_month_of_first_year.networth, first_year.networth)

    def test_no_contribution_account_compounds_monthly_to_same_annual_total(self) -> None:
        account = Account(account_id="acc_taxable", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        plan = _minimal_plan(
            accounts=[account],
            assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.from_percent(5)),
        )
        portfolios = {"acc_taxable": _portfolio(1_000_000)}

        result = _run(plan, portfolios)

        # 追加拠出のない口座は、月次複利12回でも単純な年率複利と一致する
        self.assertEqual(result.yearly_projections[0].account_balances["acc_taxable"], Money.of(1_050_000))


class CapitalGainsTaxIntegrationTest(unittest.TestCase):
    def test_no_gain_no_growth_withdrawal_is_not_taxed(self) -> None:
        account = Account(account_id="acc_taxable", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        expense = Expense(
            expense_id="expense_001", category="living", amount=Money.of(1_200_000), growth_rate=Rate.zero()
        )
        plan = _minimal_plan(
            accounts=[account],
            expenses=[expense],
            withdrawal_strategy=WithdrawalStrategy(order=[AccountType.TAXABLE]),
        )
        portfolios = {"acc_taxable": _portfolio(5_000_000, "cash")}

        result = run_projection(plan, portfolios, load_tax_rules(), load_portfolio_rules(), zero_pension_rules())
        first_year = result.yearly_projections[0]

        # 成長率0%・拠出なしなので取り崩しても含み益が生じず、譲渡税は発生しない
        self.assertEqual(first_year.capital_gains_tax, Money.zero())

    def test_growth_then_withdrawal_from_taxable_account_incurs_capital_gains_tax(self) -> None:
        account = Account(account_id="acc_taxable", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        expense = Expense(
            expense_id="expense_001", category="living", amount=Money.of(1_200_000), growth_rate=Rate.zero()
        )
        plan = _minimal_plan(
            accounts=[account],
            expenses=[expense],
            assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.from_percent(5)),
            withdrawal_strategy=WithdrawalStrategy(order=[AccountType.TAXABLE]),
        )
        portfolios = {"acc_taxable": _portfolio(5_000_000, "cash")}

        result = run_projection(plan, portfolios, load_tax_rules(), load_portfolio_rules(), zero_pension_rules())
        first_year = result.yearly_projections[0]

        # 成長率5%で口座が値上がりした状態から取り崩しが発生するため、含み益に譲渡税がかかる
        self.assertGreater(first_year.capital_gains_tax.amount, 0)

    def test_withdraw_shortfall_reports_capital_gains_tax_for_realized_gain(self) -> None:
        account = Account(account_id="acc_taxable", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        portfolio_rules = load_portfolio_rules()
        tax_rules = load_tax_rules()

        outcome = withdraw_shortfall(
            [account],
            {"acc_taxable": Money.of(2_000_000)},
            {"acc_taxable": Money.of(1_000_000)},
            Money.of(500_000),
            WithdrawalStrategy(order=[AccountType.TAXABLE]),
            portfolio_rules,
            tax_rules.capital_gains,
        )

        self.assertGreater(outcome.capital_gains_tax.amount, 0)


class AllocationPolicyIntegrationTest(unittest.TestCase):
    def test_initial_drift_is_corrected_toward_target_weights_within_first_month(self) -> None:
        from core.domain.allocation import AllocationPolicy, AllocationTarget

        equity_account = Account(account_id="acc_equity", account_type=AccountType.NISA_GROWTH, owner=OwnerType.SELF)
        bond_account = Account(account_id="acc_bond", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        allocation_policy = AllocationPolicy(
            targets=[AllocationTarget(age=0, weights={"equity_sp500": Rate.of("0.5"), "bond_us_treasury": Rate.of("0.5")})]
        )
        plan = _minimal_plan(
            accounts=[equity_account, bond_account],
            allocation_policy=allocation_policy,
        )
        equity_asset = Asset(asset_class="equity_sp500", expected_return=Rate.zero(), volatility=Rate.zero())
        bond_asset = Asset(asset_class="bond_us_treasury", expected_return=Rate.zero(), volatility=Rate.zero())
        portfolios = {
            "acc_equity": Portfolio(holdings=[Holding(asset=equity_asset, quantity=1, cost_basis=Money.of(900_000))]),
            "acc_bond": Portfolio(holdings=[Holding(asset=bond_asset, quantity=1, cost_basis=Money.of(100_000))]),
        }

        result = run_projection(
            plan, portfolios, load_tax_rules(), load_portfolio_rules(), zero_pension_rules()
        )

        first_month = result.monthly_projections[0]
        self.assertEqual(first_month.account_balances["acc_equity"], Money.of(500_000))
        self.assertEqual(first_month.account_balances["acc_bond"], Money.of(500_000))

    def test_no_allocation_policy_leaves_initial_imbalance_untouched(self) -> None:
        equity_account = Account(account_id="acc_equity", account_type=AccountType.NISA_GROWTH, owner=OwnerType.SELF)
        bond_account = Account(account_id="acc_bond", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        plan = _minimal_plan(accounts=[equity_account, bond_account])
        equity_asset = Asset(asset_class="equity_sp500", expected_return=Rate.zero(), volatility=Rate.zero())
        bond_asset = Asset(asset_class="bond_us_treasury", expected_return=Rate.zero(), volatility=Rate.zero())
        portfolios = {
            "acc_equity": Portfolio(holdings=[Holding(asset=equity_asset, quantity=1, cost_basis=Money.of(900_000))]),
            "acc_bond": Portfolio(holdings=[Holding(asset=bond_asset, quantity=1, cost_basis=Money.of(100_000))]),
        }

        result = _run(plan, portfolios)

        first_month = result.monthly_projections[0]
        self.assertEqual(first_month.account_balances["acc_equity"], Money.of(900_000))
        self.assertEqual(first_month.account_balances["acc_bond"], Money.of(100_000))


class EducationExpenseIntegrationTest(unittest.TestCase):
    def test_education_expense_is_added_only_during_applicable_age_band(self) -> None:
        from core.domain.child import Child
        from core.domain.education_expense import EducationExpenseBand

        # _minimal_planはstart_year=2026固定。子供が2020年生まれなら2026年に6歳(小学校入学)。
        child = Child(child_id="child_001", birth_date=date(2020, 4, 1))
        band = EducationExpenseBand(
            band_id="band_elementary",
            child_id="child_001",
            category="小学校",
            start_age=6,
            end_age=6,
            monthly_amount=Money.of(30_000),
        )
        plan = _minimal_plan(children=[child], education_expenses=[band])

        result = _run(plan)

        # 2026年(6歳、対象年): 月30,000円 x 12 = 360,000円が支出に加算される
        year_2026 = next(p for p in result.yearly_projections if p.year == 2026)
        self.assertEqual(year_2026.total_expense, Money.of(360_000))
        # 2027年(7歳、対象外): 加算されない
        year_2027 = next(p for p in result.yearly_projections if p.year == 2027)
        self.assertEqual(year_2027.total_expense, Money.zero())


class OneTimeExpenseIntegrationTest(unittest.TestCase):
    def test_one_time_expense_is_charged_only_in_the_triggering_month(self) -> None:
        from core.domain.one_time_expense import OneTimeExpense

        # _minimal_planはstart_condition=FIXED_DATE(2026-01-01) -> start_year=2026, start_month=1
        car_purchase = OneTimeExpense(
            expense_id="expense_car",
            category="車",
            amount=Money.of(3_000_000),
            trigger=EventCondition.at_date(date(2027, 6, 1)),
        )
        plan = _minimal_plan(one_time_expenses=[car_purchase])

        result = _run(plan)

        # 2027年6月(month_offset=17: 2年目の6ヶ月目)にのみ全額計上される
        triggering_month = next(
            p for p in result.monthly_projections if p.year == 2027 and p.month == 6
        )
        self.assertEqual(triggering_month.total_expense, Money.of(3_000_000))

        other_month = next(
            p for p in result.monthly_projections if p.year == 2027 and p.month == 5
        )
        self.assertEqual(other_month.total_expense, Money.zero())

        # 年次集計にも反映される
        year_2027 = next(p for p in result.yearly_projections if p.year == 2027)
        self.assertEqual(year_2027.total_expense, Money.of(3_000_000))

    def test_age_triggered_one_time_expense_fires_in_birthday_month(self) -> None:
        from core.domain.one_time_expense import OneTimeExpense

        user = User(birth_date=date(1990, 4, 1), residence=Prefecture.TOKYO)
        pension = Pension(
            national_pension=PensionEntitlement(estimate_annual=Money.zero()),
            employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
            claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
        )
        trip = OneTimeExpense(
            expense_id="expense_trip", category="旅行", amount=Money.of(500_000), trigger=EventCondition.at_age(37)
        )
        plan = Plan(
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
            one_time_expenses=[trip],
        )

        result = _run(plan)

        # 1990-04-01生まれが37歳になるのは2027年4月
        triggering_month = next(
            p for p in result.monthly_projections if p.year == 2027 and p.month == 4
        )
        self.assertEqual(triggering_month.total_expense, Money.of(500_000))

    def test_one_time_expense_labels_real_calendar_month_when_plan_starts_mid_year(self) -> None:
        from core.domain.one_time_expense import OneTimeExpense

        # プラン開始が7月(1月始まりではない)でも、MonthlyProjection.year/monthは
        # 実際のカレンダー通りの年月になる（year=start_year+offset_yearという単純な連番にはしない）。
        plan = _minimal_plan(
            start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 7, 1)),
            one_time_expenses=[
                OneTimeExpense(
                    expense_id="expense_car",
                    category="車",
                    amount=Money.of(3_000_000),
                    trigger=EventCondition.at_date(date(2027, 6, 1)),
                )
            ],
        )

        result = _run(plan)

        triggering_month = next(
            p for p in result.monthly_projections if p.year == 2027 and p.month == 6
        )
        self.assertEqual(triggering_month.total_expense, Money.of(3_000_000))

        # 開始月(2026年7月)はmonth_offset=0で、実際のカレンダー通りに(2026,7)とラベル付けされる
        first_month = result.monthly_projections[0]
        self.assertEqual((first_month.year, first_month.month), (2026, 7))


if __name__ == "__main__":
    unittest.main()
