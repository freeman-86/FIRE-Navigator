import unittest

from core.domain.account import Account, AccountType, OwnerType
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.portfolio_rules import AccountRules, PortfolioRules
from core.domain.value_objects import Money
from core.simulation.portfolio.account_rules import cap_contribution
from core.simulation.portfolio.portfolio_engine import allocate_discretionary_surplus, plan_fixed_contributions


def _account(account_id: str, account_type: AccountType, monthly_contribution=None) -> Account:
    return Account(
        account_id=account_id,
        account_type=account_type,
        owner=OwnerType.SELF,
        monthly_contribution=Money.of(monthly_contribution) if monthly_contribution is not None else None,
    )


class CapContributionTest(unittest.TestCase):
    def test_capped_by_annual_limit(self) -> None:
        rules = AccountRules(annual_limit=Money.of(276_000), lifetime_limit=None, tax_free=True)
        capped = cap_contribution(
            Money.of(300_000), rules, contributed_this_year=Money.zero(), lifetime_contributed=Money.zero()
        )
        self.assertEqual(capped, Money.of(276_000))

    def test_capped_by_remaining_lifetime_limit(self) -> None:
        rules = AccountRules(annual_limit=Money.of(2_400_000), lifetime_limit=Money.of(12_000_000), tax_free=True)
        capped = cap_contribution(
            Money.of(2_400_000), rules, contributed_this_year=Money.zero(), lifetime_contributed=Money.of(11_000_000)
        )
        self.assertEqual(capped, Money.of(1_000_000))

    def test_unlimited_when_no_limits(self) -> None:
        rules = AccountRules(annual_limit=None, lifetime_limit=None, tax_free=False)
        capped = cap_contribution(
            Money.of(10_000_000), rules, contributed_this_year=Money.zero(), lifetime_contributed=Money.zero()
        )
        self.assertEqual(capped, Money.of(10_000_000))


class PlanFixedContributionsTest(unittest.TestCase):
    def test_ideco_contribution_is_tax_deductible(self) -> None:
        accounts = [
            _account("acc_ideco", AccountType.IDECO, monthly_contribution=23_000),
            _account("acc_nisa", AccountType.NISA_GROWTH, monthly_contribution=50_000),
        ]
        portfolio_rules = PortfolioRules(
            rules_by_account_type={
                AccountType.IDECO: AccountRules(annual_limit=Money.of(276_000), lifetime_limit=None, tax_free=True),
                AccountType.NISA_GROWTH: AccountRules(
                    annual_limit=Money.of(2_400_000), lifetime_limit=Money.of(12_000_000), tax_free=True
                ),
            }
        )
        lifetime_contributions = {"acc_ideco": Money.zero(), "acc_nisa": Money.zero()}

        plan = plan_fixed_contributions(accounts, lifetime_contributions, portfolio_rules)

        self.assertEqual(plan.contributions["acc_ideco"], Money.of(276_000))
        self.assertEqual(plan.contributions["acc_nisa"], Money.of(600_000))
        # NISAは所得控除の対象外。iDeCo拠出額のみがtax_deductible_amountに計上される。
        self.assertEqual(plan.tax_deductible_amount, Money.of(276_000))

    def test_no_contribution_when_monthly_contribution_is_none(self) -> None:
        accounts = [_account("acc_taxable", AccountType.TAXABLE)]
        plan = plan_fixed_contributions(accounts, {"acc_taxable": Money.zero()}, PortfolioRules())
        self.assertEqual(plan.contributions, {})
        self.assertEqual(plan.tax_deductible_amount, Money.zero())


class AllocateDiscretionarySurplusTest(unittest.TestCase):
    def test_priority_order_fills_cash_target_then_nisa_then_taxable(self) -> None:
        accounts = [
            _account("acc_cash", AccountType.CASH),
            _account("acc_nisa", AccountType.NISA_GROWTH),
            _account("acc_taxable", AccountType.TAXABLE),
        ]
        account_balances = {"acc_cash": Money.of(500_000), "acc_nisa": Money.zero(), "acc_taxable": Money.zero()}
        portfolio_rules = PortfolioRules(
            rules_by_account_type={
                AccountType.NISA_GROWTH: AccountRules(
                    annual_limit=Money.of(2_400_000), lifetime_limit=Money.of(12_000_000), tax_free=True
                ),
                AccountType.TAXABLE: AccountRules(annual_limit=None, lifetime_limit=None, tax_free=False),
            }
        )
        strategy = ContributionStrategy(
            order=[AccountType.CASH, AccountType.NISA_GROWTH, AccountType.TAXABLE],
            emergency_fund_target=Money.of(1_000_000),
        )

        contributions, leftover = allocate_discretionary_surplus(
            accounts, account_balances, {"acc_cash": Money.zero(), "acc_nisa": Money.zero(), "acc_taxable": Money.zero()},
            {}, Money.of(3_000_000), strategy, portfolio_rules,
        )

        # CASHは目標1,000,000まで500,000だけ拠出、残り2,500,000がNISA上限2,400,000まで拠出、
        # 残り100,000がTAXABLE(上限なし)へ。
        self.assertEqual(contributions["acc_cash"], Money.of(500_000))
        self.assertEqual(contributions["acc_nisa"], Money.of(2_400_000))
        self.assertEqual(contributions["acc_taxable"], Money.of(100_000))
        self.assertEqual(leftover, Money.zero())

    def test_negative_surplus_allocates_nothing(self) -> None:
        accounts = [_account("acc_cash", AccountType.CASH)]
        strategy = ContributionStrategy(order=[AccountType.CASH], emergency_fund_target=Money.of(1_000_000))

        contributions, leftover = allocate_discretionary_surplus(
            accounts, {"acc_cash": Money.zero()}, {"acc_cash": Money.zero()}, {}, Money.of(-500_000), strategy, PortfolioRules()
        )

        self.assertEqual(contributions, {})
        self.assertEqual(leftover, Money.zero())

    def test_leftover_when_order_has_no_room(self) -> None:
        accounts = [_account("acc_nisa", AccountType.NISA_GROWTH)]
        portfolio_rules = PortfolioRules(
            rules_by_account_type={
                AccountType.NISA_GROWTH: AccountRules(
                    annual_limit=Money.of(100_000), lifetime_limit=None, tax_free=True
                )
            }
        )
        strategy = ContributionStrategy(order=[AccountType.NISA_GROWTH])

        contributions, leftover = allocate_discretionary_surplus(
            accounts, {"acc_nisa": Money.zero()}, {"acc_nisa": Money.zero()}, {}, Money.of(300_000), strategy, portfolio_rules
        )

        self.assertEqual(contributions["acc_nisa"], Money.of(100_000))
        self.assertEqual(leftover, Money.of(200_000))


if __name__ == "__main__":
    unittest.main()
