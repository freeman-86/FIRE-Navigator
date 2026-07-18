import unittest

from core.domain.account import Account, AccountType, OwnerType
from core.domain.value_objects import Money
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.simulation.withdrawal.withdrawal_engine import withdraw_shortfall


def _account(account_id: str, account_type: AccountType) -> Account:
    return Account(account_id=account_id, account_type=account_type, owner=OwnerType.SELF)


class WithdrawShortfallTest(unittest.TestCase):
    def test_withdraws_in_priority_order_across_multiple_accounts(self) -> None:
        accounts = [
            _account("acc_cash", AccountType.CASH),
            _account("acc_taxable", AccountType.TAXABLE),
        ]
        balances = {"acc_cash": Money.of(500_000), "acc_taxable": Money.of(5_000_000)}
        strategy = WithdrawalStrategy(order=[AccountType.CASH, AccountType.TAXABLE])

        withdrawals, unmet = withdraw_shortfall(accounts, balances, Money.of(2_000_000), strategy)

        self.assertEqual(withdrawals["acc_cash"], Money.of(500_000))
        self.assertEqual(withdrawals["acc_taxable"], Money.of(1_500_000))
        self.assertEqual(unmet, Money.zero())

    def test_never_withdraws_more_than_available_balance(self) -> None:
        accounts = [_account("acc_cash", AccountType.CASH)]
        balances = {"acc_cash": Money.of(300_000)}
        strategy = WithdrawalStrategy(order=[AccountType.CASH])

        withdrawals, unmet = withdraw_shortfall(accounts, balances, Money.of(1_000_000), strategy)

        self.assertEqual(withdrawals["acc_cash"], Money.of(300_000))
        self.assertEqual(unmet, Money.of(700_000))

    def test_account_type_not_in_order_is_never_touched(self) -> None:
        accounts = [_account("acc_ideco", AccountType.IDECO)]
        balances = {"acc_ideco": Money.of(10_000_000)}
        strategy = WithdrawalStrategy(order=[AccountType.CASH])

        withdrawals, unmet = withdraw_shortfall(accounts, balances, Money.of(500_000), strategy)

        self.assertEqual(withdrawals, {})
        self.assertEqual(unmet, Money.of(500_000))

    def test_zero_shortfall_withdraws_nothing(self) -> None:
        accounts = [_account("acc_cash", AccountType.CASH)]
        balances = {"acc_cash": Money.of(1_000_000)}
        strategy = WithdrawalStrategy(order=[AccountType.CASH])

        withdrawals, unmet = withdraw_shortfall(accounts, balances, Money.zero(), strategy)

        self.assertEqual(withdrawals, {})
        self.assertEqual(unmet, Money.zero())


if __name__ == "__main__":
    unittest.main()
