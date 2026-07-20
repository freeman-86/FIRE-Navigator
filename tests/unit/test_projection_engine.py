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
from core.simulation.projection.projection_engine import (
    DEFAULT_LIFE_EXPECTANCY_AGE,
    age_at,
    _pension_eligible_months,
    _school_year_age,
    run_projection,
)
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


def _portfolio(balance: int, asset_class: AssetClass = "equity_sp500", expected_return: Rate = None) -> Portfolio:
    # 決定論的エンジンは口座ごとのexpected_returnで資産成長させるため、成長を意図しないテストが
    # 意図せず影響を受けないよう既定は0%とする（成長を検証したいテストは明示的に指定する）。
    asset = Asset(
        asset_class=asset_class,
        expected_return=expected_return if expected_return is not None else Rate.zero(),
        volatility=Rate.from_percent(15),
    )
    holding = Holding(asset=asset, quantity=1, current_value=Money.of(balance), cost_basis=Money.of(balance))
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

    def test_horizon_uses_plans_own_life_expectancy_age_when_set(self) -> None:
        # 入力_プラン設定の想定寿命(Plan.life_expectancy_age)が設定されている場合、
        # DEFAULT_LIFE_EXPECTANCY_AGE(100)ではなくその値まで計算する。
        plan = _minimal_plan(
            milestones=[
                Milestone(
                    milestone_id="milestone_retire_001",
                    milestone_type=MilestoneType.RETIREMENT,
                    trigger=EventCondition.at_age(60),
                )
            ],
            life_expectancy_age=85,
        )
        result = _run(plan)

        expected_last_year = 1990 + 85
        self.assertEqual(result.yearly_projections[-1].year, expected_last_year)
        self.assertEqual(result.yearly_projections[-1].age_self, 85)

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
        # 決定論的エンジンは口座ごとのexpected_returnで成長させるため、投資成長率(5%)と合わせて指定する
        portfolios = {"acc_001": _portfolio(1_000_000, expected_return=Rate.from_percent(5))}

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

    def test_deterministic_engine_grows_each_account_by_its_own_expected_return(self) -> None:
        high_growth_account = Account(account_id="acc_high", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        low_growth_account = Account(account_id="acc_low", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        plan = _minimal_plan(
            accounts=[high_growth_account, low_growth_account],
            # プラン全体のinvestment_growth_rateはどちらの口座の期待リターンとも異なる値にして、
            # 口座ごとのexpected_returnが実際に使われている(投資成長率が使われていない)ことを示す
            assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.from_percent(2)),
        )
        portfolios = {
            "acc_high": _portfolio(1_000_000, expected_return=Rate.from_percent(10)),
            "acc_low": _portfolio(1_000_000, expected_return=Rate.zero()),
        }

        result = _run(plan, portfolios)
        first_year = result.yearly_projections[0]

        # 月次複利12回の端数丸めにより単純な年率10%(1,100,000)からわずかにずれる
        self.assertEqual(first_year.account_balances["acc_high"], Money.of(1_099_999))
        self.assertEqual(first_year.account_balances["acc_low"], Money.of(1_000_000))

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

        # 生年月日1990-04-01、終了条件は60歳(2050年4月に60歳の誕生日)。60歳に達する年（2050年）は
        # 1〜3月の3ヶ月分のみ収入があり(1,000,000×3/12=250,000)、翌年(2051年、61歳)は0円になる。
        by_age = {p.age_self: p.gross_income for p in result.yearly_projections}
        self.assertEqual(by_age[59], Money.of(1_000_000))
        self.assertEqual(by_age[60], Money.of(250_000))
        self.assertEqual(by_age[61], Money.zero())


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

        # 生年月日1990-04-01、標準65歳受給。65歳に達する年（2055年）は4〜12月の9ヶ月分のみ
        # 受給資格があるため、満額(1,980,000)の9/12を按分計上する（誕生日を考慮した按分）。
        # 翌年(2056年、66歳)は年間を通じて資格があるため満額になる。
        by_age = {p.age_self: p.pension_income for p in result.yearly_projections}
        self.assertEqual(by_age[64], Money.zero())
        self.assertEqual(by_age[65], Money.of(1_485_000))
        self.assertEqual(by_age[66], Money.of(1_980_000))

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
        # 生年月日1990-04-01のため、60歳に達する年（2050年）は4〜12月の9ヶ月分のみ按分計上
        # （1,504,800×9/12=1,128,600）。翌年(2051年、61歳)は満額になる。
        by_age = {p.age_self: p.pension_income for p in result.yearly_projections}
        self.assertEqual(by_age[60], Money.of(1_128_600))
        self.assertEqual(by_age[61], Money.of(1_504_800))

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
        portfolios = {"acc_taxable": _portfolio(1_000_000, expected_return=Rate.from_percent(5))}

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
        portfolios = {"acc_taxable": _portfolio(5_000_000, "cash", expected_return=Rate.from_percent(5))}

        result = run_projection(plan, portfolios, load_tax_rules(), load_portfolio_rules(), zero_pension_rules())
        first_year = result.yearly_projections[0]

        # 成長率5%で口座が値上がりした状態から取り崩しが発生するため、含み益に譲渡税がかかる
        self.assertGreater(first_year.capital_gains_tax.amount, 0)

    def test_preexisting_unrealized_gain_is_taxed_on_withdrawal(self) -> None:
        account = Account(account_id="acc_taxable", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        expense = Expense(
            expense_id="expense_001", category="living", amount=Money.of(1_200_000), growth_rate=Rate.zero()
        )
        plan = _minimal_plan(
            accounts=[account],
            expenses=[expense],
            withdrawal_strategy=WithdrawalStrategy(order=[AccountType.TAXABLE]),
        )
        # シミュレーション開始時点で既に含み益がある状態（残高5,000,000・取得原価3,000,000、
        # 入力_口座の取得原価列に相当）。成長率0%でも、この既存の含み益に対して譲渡税が発生する。
        asset = Asset(asset_class="cash", expected_return=Rate.zero(), volatility=Rate.zero())
        holding = Holding(asset=asset, quantity=1, current_value=Money.of(5_000_000), cost_basis=Money.of(3_000_000))
        portfolios = {"acc_taxable": Portfolio(holdings=[holding])}

        result = run_projection(plan, portfolios, load_tax_rules(), load_portfolio_rules(), zero_pension_rules())
        first_year = result.yearly_projections[0]

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
            65,
        )

        self.assertGreater(outcome.capital_gains_tax.amount, 0)


class AllocationPolicyIntegrationTest(unittest.TestCase):
    def test_shortfall_withdrawal_sells_overweight_asset_class_first(self) -> None:
        # 生活費不足の取り崩し以外では資産を売却しない（独立したリバランス処理は存在しない）ため、
        # オーバーウェイトな株式の売却は、実際に生活費の不足が発生した月にのみ起きることを確認する。
        from core.domain.allocation import AllocationPolicy, AllocationTarget

        equity_account = Account(account_id="acc_equity", account_type=AccountType.NISA_GROWTH, owner=OwnerType.SELF)
        bond_account = Account(account_id="acc_bond", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        allocation_policy = AllocationPolicy(
            targets=[AllocationTarget(age=0, weights={"equity_sp500": Rate.of("0.5"), "bond_us_treasury": Rate.of("0.5")})]
        )
        expense = Expense(expense_id="exp_living", category="living", amount=Money.of(1_200_000), growth_rate=Rate.zero())
        plan = _minimal_plan(
            accounts=[equity_account, bond_account],
            allocation_policy=allocation_policy,
            expenses=[expense],
        )
        equity_asset = Asset(asset_class="equity_sp500", expected_return=Rate.zero(), volatility=Rate.zero())
        bond_asset = Asset(asset_class="bond_us_treasury", expected_return=Rate.zero(), volatility=Rate.zero())
        portfolios = {
            "acc_equity": Portfolio(holdings=[Holding(asset=equity_asset, quantity=1, current_value=Money.of(900_000), cost_basis=Money.of(900_000))]),
            "acc_bond": Portfolio(holdings=[Holding(asset=bond_asset, quantity=1, current_value=Money.of(100_000), cost_basis=Money.of(100_000))]),
        }

        result = run_projection(
            plan, portfolios, load_tax_rules(), load_portfolio_rules(), zero_pension_rules()
        )

        first_month = result.monthly_projections[0]
        # 月10万円の生活費不足を、目標比率(50/50)より400,000円オーバーウェイトな株式から賄う
        # （株式だけで足りるため、目標比率通りの債券は一切取り崩されない）
        self.assertEqual(first_month.account_balances["acc_equity"], Money.of(800_000))
        self.assertEqual(first_month.account_balances["acc_bond"], Money.of(100_000))
        self.assertEqual(first_month.withdrawals_by_asset_class["equity_sp500"], Money.of(100_000))
        self.assertEqual(first_month.withdrawals_by_asset_class["bond_us_treasury"], Money.zero())

    def test_no_shortfall_leaves_initial_imbalance_untouched_even_with_allocation_policy(self) -> None:
        # 生活費の不足がない月は、配分方針が設定されていてもオーバーウェイトの解消目的だけでは
        # 一切売却しない（独立したリバランス処理は削除済み）。
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
            "acc_equity": Portfolio(holdings=[Holding(asset=equity_asset, quantity=1, current_value=Money.of(900_000), cost_basis=Money.of(900_000))]),
            "acc_bond": Portfolio(holdings=[Holding(asset=bond_asset, quantity=1, current_value=Money.of(100_000), cost_basis=Money.of(100_000))]),
        }

        result = run_projection(
            plan, portfolios, load_tax_rules(), load_portfolio_rules(), zero_pension_rules()
        )

        first_month = result.monthly_projections[0]
        self.assertEqual(first_month.account_balances["acc_equity"], Money.of(900_000))
        self.assertEqual(first_month.account_balances["acc_bond"], Money.of(100_000))

    def test_no_allocation_policy_leaves_initial_imbalance_untouched(self) -> None:
        equity_account = Account(account_id="acc_equity", account_type=AccountType.NISA_GROWTH, owner=OwnerType.SELF)
        bond_account = Account(account_id="acc_bond", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        plan = _minimal_plan(accounts=[equity_account, bond_account])
        equity_asset = Asset(asset_class="equity_sp500", expected_return=Rate.zero(), volatility=Rate.zero())
        bond_asset = Asset(asset_class="bond_us_treasury", expected_return=Rate.zero(), volatility=Rate.zero())
        portfolios = {
            "acc_equity": Portfolio(holdings=[Holding(asset=equity_asset, quantity=1, current_value=Money.of(900_000), cost_basis=Money.of(900_000))]),
            "acc_bond": Portfolio(holdings=[Holding(asset=bond_asset, quantity=1, current_value=Money.of(100_000), cost_basis=Money.of(100_000))]),
        }

        result = _run(plan, portfolios)

        first_month = result.monthly_projections[0]
        self.assertEqual(first_month.account_balances["acc_equity"], Money.of(900_000))
        self.assertEqual(first_month.account_balances["acc_bond"], Money.of(100_000))


class AgeAtMonthTest(unittest.TestCase):
    def test_switches_exactly_on_birth_month_not_january(self) -> None:
        birth_date = date(1990, 9, 1)
        # 誕生月(9月)より前は前年の年齢のまま、誕生月(1日時点)以降で切り替わる
        self.assertEqual(age_at(birth_date, 2026, 8), 35)
        self.assertEqual(age_at(birth_date, 2026, 9), 36)
        self.assertEqual(age_at(birth_date, 2026, 12), 36)
        self.assertEqual(age_at(birth_date, 2027, 1), 36)

    def test_reference_is_the_first_of_the_month_so_late_birthday_delays_switch(self) -> None:
        birth_date = date(1990, 9, 15)
        # 参照日は各月の1日のため、9月1日時点ではまだ誕生日(9/15)を迎えておらず35歳のまま
        self.assertEqual(age_at(birth_date, 2026, 9), 35)
        self.assertEqual(age_at(birth_date, 2026, 10), 36)

    def test_returns_zero_before_birth(self) -> None:
        self.assertEqual(age_at(date(2030, 1, 1), 2026, 1), 0)


class PensionEligibleMonthsTest(unittest.TestCase):
    def test_counts_only_months_from_birth_month_in_transition_year(self) -> None:
        # 1990-04-01生まれ、65歳受給。2055年度中に65歳の誕生日(4/1)を迎えるため、
        # 4月〜12月の9ヶ月分のみ資格がある(1〜3月はまだ64歳)。
        birth_date = date(1990, 4, 1)
        month_pairs = [(2055, m) for m in range(1, 13)]
        self.assertEqual(_pension_eligible_months(birth_date, 65, month_pairs), 9)

    def test_counts_all_twelve_months_once_fully_eligible(self) -> None:
        birth_date = date(1990, 4, 1)
        month_pairs = [(2056, m) for m in range(1, 13)]
        self.assertEqual(_pension_eligible_months(birth_date, 65, month_pairs), 12)

    def test_counts_zero_months_before_eligible(self) -> None:
        birth_date = date(1990, 4, 1)
        month_pairs = [(2054, m) for m in range(1, 13)]
        self.assertEqual(_pension_eligible_months(birth_date, 65, month_pairs), 0)


class SchoolYearAgeTest(unittest.TestCase):
    def test_born_on_april_first_switches_exactly_at_april(self) -> None:
        birth_date = date(2020, 4, 1)
        # 2026年3月(2025年度): 4/1(2025-04-01)時点でまだ5歳
        self.assertEqual(_school_year_age(birth_date, 2026, 3), 5)
        # 2026年4月(2026年度): 4/1(2026-04-01)時点で6歳
        self.assertEqual(_school_year_age(birth_date, 2026, 4), 6)

    def test_birth_month_does_not_affect_switch_timing(self) -> None:
        birth_date = date(2019, 9, 1)
        # 誕生日(9月)を過ぎていても、4月を跨がなければ学年年齢は変わらない
        self.assertEqual(_school_year_age(birth_date, 2025, 12), 5)
        self.assertEqual(_school_year_age(birth_date, 2026, 3), 5)
        self.assertEqual(_school_year_age(birth_date, 2026, 4), 6)

    def test_returns_none_before_birth(self) -> None:
        birth_date = date(2025, 6, 1)
        self.assertIsNone(_school_year_age(birth_date, 2025, 4))
        self.assertIsNone(_school_year_age(birth_date, 2026, 3))
        self.assertEqual(_school_year_age(birth_date, 2026, 4), 0)


class EducationExpenseIntegrationTest(unittest.TestCase):
    def test_education_expense_switches_at_april_not_birth_month(self) -> None:
        from core.domain.child import Child
        from core.domain.education_expense import EducationExpenseBand

        # 誕生日は9月(2019-09-01)。誕生日基準なら6歳になるのは2025年9月だが、
        # 学年(4月1日)基準では2026年度(2026年4月〜)にならないと4/1時点で6歳に到達しない
        # （2025年度の4/1時点ではまだ5歳）。切り替わりが誕生月(9月)ではなく4月であることを確認する。
        child = Child(child_id="child_001", birth_date=date(2019, 9, 1))
        band = EducationExpenseBand(
            band_id="band_elementary",
            child_id="child_001",
            category="小学校",
            start_age=6,
            end_age=11,
            monthly_amount=Money.of(30_000),
        )
        plan = _minimal_plan(children=[child], education_expenses=[band])

        result = _run(plan)

        # 2026年3月(2025年度、4/1時点で5歳): 対象外
        march_2026 = next(p for p in result.monthly_projections if p.year == 2026 and p.month == 3)
        self.assertEqual(march_2026.total_expense, Money.zero())
        # 2025年9月の誕生日を過ぎていても、4月を跨がなければ切り替わらない
        # 2026年4月(2026年度、4/1時点で6歳): 対象
        april_2026 = next(p for p in result.monthly_projections if p.year == 2026 and p.month == 4)
        self.assertEqual(april_2026.total_expense, Money.of(30_000))

    def test_education_expense_is_added_only_during_applicable_age_band(self) -> None:
        from core.domain.child import Child
        from core.domain.education_expense import EducationExpenseBand

        # 誕生日がちょうど4月1日の子供 -> 学年年齢の切り替わりが分かりやすい。
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

        # 2026年1〜3月(2025年度の4/1時点で5歳、対象外)
        for month in (1, 2, 3):
            projection = next(p for p in result.monthly_projections if p.year == 2026 and p.month == month)
            self.assertEqual(projection.total_expense, Money.zero(), f"2026年{month}月")
        # 2026年4〜12月(2026年度の4/1時点で6歳、対象)
        for month in range(4, 13):
            projection = next(p for p in result.monthly_projections if p.year == 2026 and p.month == month)
            self.assertEqual(projection.total_expense, Money.of(30_000), f"2026年{month}月")
        # 2027年1〜3月(2026年度のまま、6歳、対象)
        for month in (1, 2, 3):
            projection = next(p for p in result.monthly_projections if p.year == 2027 and p.month == month)
            self.assertEqual(projection.total_expense, Money.of(30_000), f"2027年{month}月")
        # 2027年4月以降(2027年度の4/1時点で7歳、対象外)
        april_2027 = next(p for p in result.monthly_projections if p.year == 2027 and p.month == 4)
        self.assertEqual(april_2027.total_expense, Money.zero())


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
