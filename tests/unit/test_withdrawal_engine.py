import unittest
from decimal import Decimal

from core.domain.account import Account, AccountType, OwnerType
from core.domain.portfolio_rules import AccountRules, PortfolioRules
from core.domain.tax_config import CapitalGainsTaxRules
from core.domain.value_objects import Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.simulation.withdrawal.withdrawal_engine import withdraw_shortfall

ZERO_TAX = CapitalGainsTaxRules(rate=Rate.zero())
STANDARD_RATE = CapitalGainsTaxRules(rate=Rate.of("0.20315"))


def _account(account_id: str, account_type: AccountType) -> Account:
    return Account(account_id=account_id, account_type=account_type, owner=OwnerType.SELF)


def _rules(tax_free_by_type: dict[AccountType, bool]) -> PortfolioRules:
    return PortfolioRules(
        rules_by_account_type={
            account_type: AccountRules(annual_limit=None, lifetime_limit=None, tax_free=tax_free)
            for account_type, tax_free in tax_free_by_type.items()
        }
    )


ANY_AGE = 65


class WithdrawShortfallTest(unittest.TestCase):
    def test_withdraws_in_priority_order_across_multiple_accounts(self) -> None:
        accounts = [
            _account("acc_cash", AccountType.CASH),
            _account("acc_taxable", AccountType.TAXABLE),
        ]
        balances = {"acc_cash": Money.of(500_000), "acc_taxable": Money.of(5_000_000)}
        cost_basis = {"acc_cash": Money.of(500_000), "acc_taxable": Money.of(5_000_000)}
        strategy = WithdrawalStrategy(order=[AccountType.CASH, AccountType.TAXABLE])
        rules = _rules({AccountType.CASH: True, AccountType.TAXABLE: False})

        outcome = withdraw_shortfall(accounts, balances, cost_basis, Money.of(2_000_000), strategy, rules, ZERO_TAX, ANY_AGE)

        self.assertEqual(outcome.withdrawals["acc_cash"], Money.of(500_000))
        self.assertEqual(outcome.withdrawals["acc_taxable"], Money.of(1_500_000))
        self.assertEqual(outcome.remaining_shortfall, Money.zero())
        self.assertEqual(outcome.capital_gains_tax, Money.zero())

    def test_never_withdraws_more_than_available_balance(self) -> None:
        accounts = [_account("acc_cash", AccountType.CASH)]
        balances = {"acc_cash": Money.of(300_000)}
        cost_basis = {"acc_cash": Money.of(300_000)}
        strategy = WithdrawalStrategy(order=[AccountType.CASH])
        rules = _rules({AccountType.CASH: True})

        outcome = withdraw_shortfall(accounts, balances, cost_basis, Money.of(1_000_000), strategy, rules, ZERO_TAX, ANY_AGE)

        self.assertEqual(outcome.withdrawals["acc_cash"], Money.of(300_000))
        self.assertEqual(outcome.remaining_shortfall, Money.of(700_000))

    def test_account_type_not_in_order_is_never_touched(self) -> None:
        accounts = [_account("acc_ideco", AccountType.IDECO)]
        balances = {"acc_ideco": Money.of(10_000_000)}
        cost_basis = {"acc_ideco": Money.of(10_000_000)}
        strategy = WithdrawalStrategy(order=[AccountType.CASH])
        rules = _rules({AccountType.CASH: True, AccountType.IDECO: True})

        outcome = withdraw_shortfall(accounts, balances, cost_basis, Money.of(500_000), strategy, rules, ZERO_TAX, ANY_AGE)

        self.assertEqual(outcome.withdrawals, {})
        self.assertEqual(outcome.remaining_shortfall, Money.of(500_000))

    def test_zero_shortfall_withdraws_nothing(self) -> None:
        accounts = [_account("acc_cash", AccountType.CASH)]
        balances = {"acc_cash": Money.of(1_000_000)}
        cost_basis = {"acc_cash": Money.of(1_000_000)}
        strategy = WithdrawalStrategy(order=[AccountType.CASH])
        rules = _rules({AccountType.CASH: True})

        outcome = withdraw_shortfall(accounts, balances, cost_basis, Money.zero(), strategy, rules, ZERO_TAX, ANY_AGE)

        self.assertEqual(outcome.withdrawals, {})
        self.assertEqual(outcome.remaining_shortfall, Money.zero())


class CapitalGainsTaxTest(unittest.TestCase):
    def test_nisa_withdrawal_is_never_taxed_even_with_unrealized_gain(self) -> None:
        accounts = [_account("acc_nisa", AccountType.NISA_GROWTH)]
        balances = {"acc_nisa": Money.of(2_000_000)}
        cost_basis = {"acc_nisa": Money.of(1_000_000)}  # 含み益100万円
        strategy = WithdrawalStrategy(order=[AccountType.NISA_GROWTH])
        rules = _rules({AccountType.NISA_GROWTH: True})

        outcome = withdraw_shortfall(accounts, balances, cost_basis, Money.of(500_000), strategy, rules, STANDARD_RATE, ANY_AGE)

        self.assertEqual(outcome.withdrawals["acc_nisa"], Money.of(500_000))
        self.assertEqual(outcome.capital_gains_tax, Money.zero())
        self.assertEqual(outcome.remaining_shortfall, Money.zero())

    def test_taxable_withdrawal_with_unrealized_gain_is_grossed_up(self) -> None:
        # 残高200万円、取得原価100万円 -> 含み益割合50%
        accounts = [_account("acc_taxable", AccountType.TAXABLE)]
        balances = {"acc_taxable": Money.of(2_000_000)}
        cost_basis = {"acc_taxable": Money.of(1_000_000)}
        strategy = WithdrawalStrategy(order=[AccountType.TAXABLE])
        rules = _rules({AccountType.TAXABLE: False})
        target_net = Money.of(500_000)

        outcome = withdraw_shortfall(accounts, balances, cost_basis, target_net, strategy, rules, STANDARD_RATE, ANY_AGE)

        # 手取り50万円を満たすには、税込みでそれより多く取り崩す必要がある
        gross = outcome.withdrawals["acc_taxable"]
        self.assertGreater(gross.amount, target_net.amount)
        self.assertEqual(outcome.remaining_shortfall, Money.zero())

        # 実現益 = 取り崩し額 × 含み益割合(50%)、税 = 実現益 × 20.315%
        expected_gain = Money.of(gross.amount * Decimal("0.5"))
        expected_tax = Money.of(expected_gain.amount * Decimal("0.20315"))
        self.assertEqual(outcome.capital_gains_tax, expected_tax)
        # 手取り = 総額 - 税額（グロスアップ過程の円未満丸めにより1円程度の誤差はありうる）
        self.assertAlmostEqual(int((gross - outcome.capital_gains_tax).amount), int(target_net.amount), delta=1)

    def test_taxable_withdrawal_with_unrealized_loss_is_not_taxed(self) -> None:
        # 残高80万円、取得原価100万円 -> 含み損
        accounts = [_account("acc_taxable", AccountType.TAXABLE)]
        balances = {"acc_taxable": Money.of(800_000)}
        cost_basis = {"acc_taxable": Money.of(1_000_000)}
        strategy = WithdrawalStrategy(order=[AccountType.TAXABLE])
        rules = _rules({AccountType.TAXABLE: False})

        outcome = withdraw_shortfall(
            accounts, balances, cost_basis, Money.of(300_000), strategy, rules, STANDARD_RATE, ANY_AGE
        )

        self.assertEqual(outcome.withdrawals["acc_taxable"], Money.of(300_000))
        self.assertEqual(outcome.capital_gains_tax, Money.zero())

    def test_cost_basis_reduces_proportionally_after_partial_withdrawal(self) -> None:
        accounts = [_account("acc_taxable", AccountType.TAXABLE)]
        balances = {"acc_taxable": Money.of(1_000_000)}
        cost_basis = {"acc_taxable": Money.of(400_000)}
        strategy = WithdrawalStrategy(order=[AccountType.TAXABLE])
        rules = _rules({AccountType.TAXABLE: False})

        outcome = withdraw_shortfall(
            accounts, balances, cost_basis, Money.of(100_000), strategy, rules, ZERO_TAX, ANY_AGE
        )

        # 税率0%なので取り崩し額はそのまま10万円、残高の10%を取り崩したことになる
        self.assertEqual(outcome.withdrawals["acc_taxable"], Money.of(100_000))
        # 取得原価も同じ割合(10%)だけ減る: 400,000 * 0.9 = 360,000
        self.assertEqual(outcome.updated_cost_basis["acc_taxable"], Money.of(360_000))

    def test_full_withdrawal_of_taxable_account_taxes_entire_unrealized_gain(self) -> None:
        accounts = [_account("acc_taxable", AccountType.TAXABLE)]
        balances = {"acc_taxable": Money.of(1_000_000)}
        cost_basis = {"acc_taxable": Money.of(600_000)}
        strategy = WithdrawalStrategy(order=[AccountType.TAXABLE])
        rules = _rules({AccountType.TAXABLE: False})
        # 手取りベースで口座の最大手取り額を大きく超える不足額をぶつける
        outcome = withdraw_shortfall(
            accounts, balances, cost_basis, Money.of(100_000_000), strategy, rules, STANDARD_RATE, ANY_AGE
        )

        self.assertEqual(outcome.withdrawals["acc_taxable"], Money.of(1_000_000))
        expected_tax = Money.of(400_000 * Decimal("0.20315"))
        self.assertEqual(outcome.capital_gains_tax, expected_tax)
        self.assertEqual(outcome.updated_cost_basis["acc_taxable"], Money.zero())
        self.assertGreater(outcome.remaining_shortfall, Money.zero())


def _rules_with_min_age(entries: dict[AccountType, tuple[bool, "int | None"]]) -> PortfolioRules:
    return PortfolioRules(
        rules_by_account_type={
            account_type: AccountRules(
                annual_limit=None, lifetime_limit=None, tax_free=tax_free, min_withdrawal_age=min_age
            )
            for account_type, (tax_free, min_age) in entries.items()
        }
    )


class MinWithdrawalAgeTest(unittest.TestCase):
    def test_skips_age_restricted_account_and_uses_next_eligible_account(self) -> None:
        accounts = [
            _account("acc_ideco", AccountType.IDECO),
            _account("acc_cash", AccountType.CASH),
        ]
        balances = {"acc_ideco": Money.of(10_000_000), "acc_cash": Money.of(500_000)}
        cost_basis = {"acc_ideco": Money.of(10_000_000), "acc_cash": Money.of(500_000)}
        strategy = WithdrawalStrategy(order=[AccountType.CASH, AccountType.IDECO])
        rules = _rules_with_min_age({AccountType.CASH: (True, None), AccountType.IDECO: (True, 60)})

        outcome = withdraw_shortfall(accounts, balances, cost_basis, Money.of(300_000), strategy, rules, ZERO_TAX, 45)

        self.assertEqual(outcome.withdrawals, {"acc_cash": Money.of(300_000)})

    def test_only_age_locked_balance_leaves_shortfall_unmet(self) -> None:
        accounts = [_account("acc_ideco", AccountType.IDECO)]
        balances = {"acc_ideco": Money.of(10_000_000)}
        cost_basis = {"acc_ideco": Money.of(10_000_000)}
        strategy = WithdrawalStrategy(order=[AccountType.IDECO])
        rules = _rules_with_min_age({AccountType.IDECO: (True, 60)})

        outcome = withdraw_shortfall(accounts, balances, cost_basis, Money.of(300_000), strategy, rules, ZERO_TAX, 45)

        self.assertEqual(outcome.withdrawals, {})
        self.assertEqual(outcome.remaining_shortfall, Money.of(300_000))

    def test_age_restricted_account_is_usable_once_min_age_reached(self) -> None:
        accounts = [_account("acc_ideco", AccountType.IDECO)]
        balances = {"acc_ideco": Money.of(10_000_000)}
        cost_basis = {"acc_ideco": Money.of(10_000_000)}
        strategy = WithdrawalStrategy(order=[AccountType.IDECO])
        rules = _rules_with_min_age({AccountType.IDECO: (True, 60)})

        outcome = withdraw_shortfall(accounts, balances, cost_basis, Money.of(300_000), strategy, rules, ZERO_TAX, 60)

        self.assertEqual(outcome.withdrawals, {"acc_ideco": Money.of(300_000)})


if __name__ == "__main__":
    unittest.main()
