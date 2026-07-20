from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from core.domain.account import Account, AccountType
from core.domain.portfolio_rules import PortfolioRules
from core.domain.tax_config import CapitalGainsTaxRules
from core.domain.value_objects import Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy


@dataclass
class WithdrawalOutcome:
    withdrawals: dict[str, Money] = field(default_factory=dict)
    updated_cost_basis: dict[str, Money] = field(default_factory=dict)
    capital_gains_tax: Money = field(default_factory=Money.zero)
    remaining_shortfall: Money = field(default_factory=Money.zero)


def withdraw_shortfall(
    accounts: list[Account],
    account_balances: dict[str, Money],
    cost_basis_balances: dict[str, Money],
    net_shortfall: Money,
    withdrawal_strategy: WithdrawalStrategy,
    portfolio_rules: PortfolioRules,
    capital_gains_tax_rules: CapitalGainsTaxRules,
    age: int,
) -> WithdrawalOutcome:
    """収入だけでは賄えない不足額(net_shortfall、手取りベース)を、withdrawal_strategy.orderの
    優先順位で口座残高から取り崩す。口座残高を超えて取り崩すことはない。

    課税口座（portfolio_rulesでtax_free=falseと判定される口座タイプ。設計上はTAXABLEのみが該当）
    からの取り崩しは、平均取得原価方式で実現益を算出し、capital_gains_tax_rules.rateで譲渡税を
    課税する。含み損（実現益がマイナス）の場合は課税しない（損益通算・繰越控除は対象外という
    簡易化。ギャップ分析6章で確定）。net_shortfallは手取りベースの目標額のため、課税口座からは
    税額を上乗せした総額を取り崩す（グロスアップ）。

    ageがportfolio_rulesのmin_withdrawal_age未満の口座タイプ（iDeCo/企業型DC等）はそもそも
    取り崩し対象から除外し、他の口座で不足分を賄う。それでも賄いきれない場合、その分は
    remaining_shortfallとして残り続ける（口座を強制的に取り崩すことはしない）。

    戻り値のWithdrawalOutcome:
    - withdrawals: 口座ごとの取り崩し総額（税引き前）
    - updated_cost_basis: 取り崩し後の口座ごとの累計取得原価
    - capital_gains_tax: 発生した譲渡税の合計
    - remaining_shortfall: 取り崩しきれなかった残り（手取りベース）
    """

    remaining_net = net_shortfall if not net_shortfall.is_negative else Money.zero()
    withdrawals: dict[str, Money] = {}
    updated_cost_basis = dict(cost_basis_balances)
    total_capital_gains_tax = Money.zero()

    accounts_by_type: dict[AccountType, list[Account]] = {}
    for account in accounts:
        accounts_by_type.setdefault(account.account_type, []).append(account)

    for account_type in withdrawal_strategy.order:
        if remaining_net == Money.zero():
            break
        rules = portfolio_rules.rules_for(account_type)
        if rules.min_withdrawal_age is not None and age < rules.min_withdrawal_age:
            continue
        is_taxable = not rules.tax_free
        for account in accounts_by_type.get(account_type, []):
            if remaining_net == Money.zero():
                break
            available = account_balances.get(account.account_id, Money.zero())
            if available.is_negative or available == Money.zero():
                continue

            cost_basis = updated_cost_basis.get(account.account_id, Money.zero())
            take_gross, take_net, tax = withdraw_from_single_account(
                available, cost_basis, remaining_net, is_taxable, capital_gains_tax_rules.rate
            )
            if take_gross == Money.zero():
                continue

            withdrawals[account.account_id] = withdrawals.get(account.account_id, Money.zero()) + take_gross
            remaining_net = remaining_net - take_net
            total_capital_gains_tax = total_capital_gains_tax + tax
            updated_cost_basis[account.account_id] = reduce_cost_basis_proportionally(
                cost_basis, available, take_gross
            )

    return WithdrawalOutcome(
        withdrawals=withdrawals,
        updated_cost_basis=updated_cost_basis,
        capital_gains_tax=total_capital_gains_tax,
        remaining_shortfall=remaining_net,
    )


def withdraw_from_single_account(
    available: Money,
    cost_basis: Money,
    remaining_net: Money,
    is_taxable: bool,
    rate: Rate,
) -> tuple[Money, Money, Money]:
    """1口座から取り崩す(総額, 手取り換算額, 譲渡税)を決める。remaining_netを満たせるだけ
    取り崩すが、口座残高(available)を超えない範囲に収める。
    """

    if not is_taxable:
        take_gross = available if available < remaining_net else remaining_net
        return take_gross, take_gross, Money.zero()

    gain_ratio = _gain_ratio(available, cost_basis)
    if gain_ratio <= 0:
        take_gross = available if available < remaining_net else remaining_net
        return take_gross, take_gross, Money.zero()

    net_factor = Decimal(1) - gain_ratio * rate.value
    max_net_from_account = Money.of(available.amount * net_factor)

    if max_net_from_account <= remaining_net:
        take_gross = available
        take_net = max_net_from_account
    else:
        take_net = remaining_net
        take_gross = Money.of(take_net.amount / net_factor)

    realized_gain = Money.of(take_gross.amount * gain_ratio)
    tax = Money.of(realized_gain.amount * rate.value)
    return take_gross, take_net, tax


def _gain_ratio(available: Money, cost_basis: Money) -> Decimal:
    if available == Money.zero():
        return Decimal(0)
    return Decimal(1) - (cost_basis.amount / available.amount)


def reduce_cost_basis_proportionally(cost_basis: Money, available_before: Money, take_gross: Money) -> Money:
    if available_before == Money.zero():
        return Money.zero()
    consumed_fraction = take_gross.amount / available_before.amount
    reduced = cost_basis.amount * (Decimal(1) - consumed_fraction)
    return Money.of(reduced if reduced > 0 else Decimal(0))
