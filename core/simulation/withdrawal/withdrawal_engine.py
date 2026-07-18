from __future__ import annotations

from core.domain.account import Account, AccountType
from core.domain.value_objects import Money
from core.domain.withdrawal_strategy import WithdrawalStrategy


def withdraw_shortfall(
    accounts: list[Account],
    account_balances: dict[str, Money],
    shortfall: Money,
    withdrawal_strategy: WithdrawalStrategy,
) -> tuple[dict[str, Money], Money]:
    """収入だけでは賄えない不足額(shortfall)を、withdrawal_strategy.orderの優先順位で
    口座残高から取り崩す。口座残高を超えて取り崩すことはない。

    戻り値は (口座ごとの取り崩し額(正の値), 取り崩しきれなかった残り)。
    取り崩し額に伴う税金（含み益への課税等）はまだ考慮しない（Sprint8時点のMVP簡略化）。
    """

    remaining = shortfall if not shortfall.is_negative else Money.zero()
    withdrawals: dict[str, Money] = {}

    accounts_by_type: dict[AccountType, list[Account]] = {}
    for account in accounts:
        accounts_by_type.setdefault(account.account_type, []).append(account)

    for account_type in withdrawal_strategy.order:
        if remaining == Money.zero():
            break
        for account in accounts_by_type.get(account_type, []):
            if remaining == Money.zero():
                break
            available = account_balances.get(account.account_id, Money.zero())
            if not available.is_negative:
                take = available if available < remaining else remaining
            else:
                take = Money.zero()
            if take == Money.zero():
                continue
            withdrawals[account.account_id] = withdrawals.get(account.account_id, Money.zero()) + take
            remaining = remaining - take

    return withdrawals, remaining
