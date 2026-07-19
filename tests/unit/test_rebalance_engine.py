import unittest
from datetime import date

from core.domain.account import Account, AccountType, OwnerType
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio_rules import AccountRules, PortfolioRules
from core.domain.tax_config import CapitalGainsTaxRules
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.simulation.portfolio.rebalance_engine import rebalance

ZERO_TAX = CapitalGainsTaxRules(rate=Rate.zero())
STANDARD_RATE = CapitalGainsTaxRules(rate=Rate.of("0.20315"))


def _plan(accounts: list[Account]) -> Plan:
    user = User(birth_date=date(1990, 4, 1), residence=Prefecture.TOKYO)
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )
    return Plan(
        plan_id="plan_test",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.TODAY),
        assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.zero()),
        accounts=accounts,
        tax_config=TaxConfig(residence=Prefecture.TOKYO),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
        contribution_strategy=ContributionStrategy(order=[]),
    )


class RebalanceTest(unittest.TestCase):
    def test_no_target_weights_is_a_no_op(self) -> None:
        accounts = [Account(account_id="acc_a", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)]
        plan = _plan(accounts)
        balances = {"acc_a": Money.of(1_000_000)}
        cost_basis = {"acc_a": Money.of(1_000_000)}

        outcome = rebalance(plan, balances, cost_basis, {}, {"acc_a": "equity_sp500"}, {}, PortfolioRules(), ZERO_TAX)

        self.assertEqual(outcome.account_balances, balances)
        self.assertEqual(outcome.capital_gains_tax, Money.zero())

    def test_sells_overweight_and_buys_underweight_across_accounts(self) -> None:
        equity_account = Account(account_id="acc_equity", account_type=AccountType.NISA_GROWTH, owner=OwnerType.SELF)
        bond_account = Account(account_id="acc_bond", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        plan = _plan([equity_account, bond_account])
        # 現在: 株式90%(900,000)・債券10%(100,000)。目標は50%/50%。
        balances = {"acc_equity": Money.of(900_000), "acc_bond": Money.of(100_000)}
        cost_basis = {"acc_equity": Money.of(900_000), "acc_bond": Money.of(100_000)}
        asset_class_by_account_id = {"acc_equity": "equity_sp500", "acc_bond": "bond_us_treasury"}
        target_weights = {"equity_sp500": Rate.of("0.5"), "bond_us_treasury": Rate.of("0.5")}
        portfolio_rules = PortfolioRules(
            rules_by_account_type={
                AccountType.NISA_GROWTH: AccountRules(annual_limit=None, lifetime_limit=None, tax_free=True),
                AccountType.TAXABLE: AccountRules(annual_limit=None, lifetime_limit=None, tax_free=False),
            }
        )

        outcome = rebalance(
            plan, balances, cost_basis, {}, asset_class_by_account_id, target_weights, portfolio_rules, ZERO_TAX
        )

        # 株式から400,000売却され債券へ再投資、結果的に50%/50%に近づく
        self.assertEqual(outcome.account_balances["acc_equity"], Money.of(500_000))
        self.assertEqual(outcome.account_balances["acc_bond"], Money.of(500_000))
        self.assertEqual(outcome.unreinvested_proceeds, Money.zero())

    def test_taxable_overweight_sale_incurs_capital_gains_tax(self) -> None:
        equity_account = Account(account_id="acc_equity", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        bond_account = Account(account_id="acc_bond", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        plan = _plan([equity_account, bond_account])
        # 課税口座の株式に含み益あり(残高900,000・取得原価450,000)
        balances = {"acc_equity": Money.of(900_000), "acc_bond": Money.of(100_000)}
        cost_basis = {"acc_equity": Money.of(450_000), "acc_bond": Money.of(100_000)}
        asset_class_by_account_id = {"acc_equity": "equity_sp500", "acc_bond": "bond_us_treasury"}
        target_weights = {"equity_sp500": Rate.of("0.5"), "bond_us_treasury": Rate.of("0.5")}
        portfolio_rules = PortfolioRules(
            rules_by_account_type={
                AccountType.TAXABLE: AccountRules(annual_limit=None, lifetime_limit=None, tax_free=False),
            }
        )

        outcome = rebalance(
            plan, balances, cost_basis, {}, asset_class_by_account_id, target_weights, portfolio_rules, STANDARD_RATE
        )

        self.assertGreater(outcome.capital_gains_tax.amount, 0)

    def test_prefers_selling_tax_free_account_over_taxable_for_same_asset_class(self) -> None:
        nisa_equity = Account(account_id="acc_nisa_equity", account_type=AccountType.NISA_GROWTH, owner=OwnerType.SELF)
        taxable_equity = Account(account_id="acc_taxable_equity", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        bond_account = Account(account_id="acc_bond", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)
        plan = _plan([nisa_equity, taxable_equity, bond_account])
        balances = {"acc_nisa_equity": Money.of(500_000), "acc_taxable_equity": Money.of(400_000), "acc_bond": Money.of(100_000)}
        cost_basis = {"acc_nisa_equity": Money.of(200_000), "acc_taxable_equity": Money.of(100_000), "acc_bond": Money.of(100_000)}
        asset_class_by_account_id = {
            "acc_nisa_equity": "equity_sp500", "acc_taxable_equity": "equity_sp500", "acc_bond": "bond_us_treasury",
        }
        target_weights = {"equity_sp500": Rate.of("0.5"), "bond_us_treasury": Rate.of("0.5")}
        portfolio_rules = PortfolioRules(
            rules_by_account_type={
                AccountType.NISA_GROWTH: AccountRules(annual_limit=None, lifetime_limit=None, tax_free=True),
                AccountType.TAXABLE: AccountRules(annual_limit=None, lifetime_limit=None, tax_free=False),
            }
        )

        outcome = rebalance(
            plan, balances, cost_basis, {}, asset_class_by_account_id, target_weights, portfolio_rules, STANDARD_RATE
        )

        # 株式合計900,000のうち400,000を売却する必要があるが、非課税のNISA(500,000)だけで賄えるため
        # 課税口座(acc_taxable_equity)は一切売却されず、譲渡税も発生しない
        self.assertEqual(outcome.account_balances["acc_taxable_equity"], Money.of(400_000))
        self.assertEqual(outcome.capital_gains_tax, Money.zero())


if __name__ == "__main__":
    unittest.main()
