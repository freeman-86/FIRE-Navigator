from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from core.domain.account import Account, AccountType
from core.domain.asset import AssetClass
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
    withdrawals_by_asset_class: dict[str, Money] = field(default_factory=dict)


def withdraw_shortfall(
    accounts: list[Account],
    account_balances: dict[str, Money],
    cost_basis_balances: dict[str, Money],
    net_shortfall: Money,
    withdrawal_strategy: WithdrawalStrategy,
    portfolio_rules: PortfolioRules,
    capital_gains_tax_rules: CapitalGainsTaxRules,
    age: int,
    asset_class_by_account_id: Optional[dict[str, AssetClass]] = None,
    target_weights: Optional[dict[AssetClass, Rate]] = None,
) -> WithdrawalOutcome:
    """収入だけでは賄えない不足額(net_shortfall、手取りベース)を口座残高から取り崩す。
    口座残高を超えて取り崩すことはない。生活費の取り崩しとリバランス（資産配分の是正）を
    1つの処理に統合しており、独立した「売却して買い直す」リバランス処理は存在しない
    （新規拠出のドリフト考慮配分と、この取り崩し時のオーバーウェイト優先売却だけで、
    長期的に目標配分へ近づける設計）。

    asset_class_by_account_id/target_weights（入力_配分方針が設定されている場合の
    年齢時点の目標比率）が両方渡された場合、まず目標比率より多く保有している資産クラス
    （オーバーウェイトな資産）から優先して取り崩す（超過分＝オーバーウェイト額を上限とする）。
    それでも不足が残る場合、または配分方針が未設定/どの資産クラスもオーバーウェイトでない場合は、
    従来通りwithdrawal_strategy.orderの口座タイプ優先順位（現金→課税口座→NISA→iDeCo等）で
    残りを取り崩す。

    資産クラス内でどの口座から売るかは、withdrawal_strategy.orderの順（課税口座を先に、
    非課税口座は課税口座を使い切ってから）とする。

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
    - withdrawals_by_asset_class: 資産クラスごとの取り崩し総額（税引き前）
    """

    remaining_net = net_shortfall if not net_shortfall.is_negative else Money.zero()
    withdrawals: dict[str, Money] = {}
    withdrawals_by_asset_class: dict[str, Money] = {}
    updated_cost_basis = dict(cost_basis_balances)
    balances = dict(account_balances)
    total_capital_gains_tax = Money.zero()

    def _is_eligible(account_type: AccountType) -> bool:
        min_age = portfolio_rules.rules_for(account_type).min_withdrawal_age
        return min_age is None or age >= min_age

    def _sell(account: Account, target: Money) -> Money:
        nonlocal remaining_net, total_capital_gains_tax
        available = balances.get(account.account_id, Money.zero())
        if available.is_negative or available == Money.zero() or target == Money.zero():
            return Money.zero()
        is_taxable = not portfolio_rules.rules_for(account.account_type).tax_free
        cost_basis = updated_cost_basis.get(account.account_id, Money.zero())
        take_gross, take_net, tax = withdraw_from_single_account(
            available, cost_basis, target, is_taxable, capital_gains_tax_rules.rate
        )
        if take_gross == Money.zero():
            return Money.zero()

        withdrawals[account.account_id] = withdrawals.get(account.account_id, Money.zero()) + take_gross
        updated_cost_basis[account.account_id] = reduce_cost_basis_proportionally(cost_basis, available, take_gross)
        balances[account.account_id] = available - take_gross
        remaining_net = remaining_net - take_net
        total_capital_gains_tax = total_capital_gains_tax + tax
        if asset_class_by_account_id is not None:
            asset_class = asset_class_by_account_id.get(account.account_id)
            if asset_class is not None:
                withdrawals_by_asset_class[asset_class] = (
                    withdrawals_by_asset_class.get(asset_class, Money.zero()) + take_gross
                )
        return take_net

    accounts_by_type: dict[AccountType, list[Account]] = {}
    for account in accounts:
        accounts_by_type.setdefault(account.account_type, []).append(account)

    if asset_class_by_account_id and target_weights:
        order_index = {account_type: index for index, account_type in enumerate(withdrawal_strategy.order)}
        accounts_by_asset_class: dict[AssetClass, list[Account]] = {}
        for account in accounts:
            asset_class = asset_class_by_account_id.get(account.account_id)
            if asset_class is not None:
                accounts_by_asset_class.setdefault(asset_class, []).append(account)

        total_value = sum(balances.values(), Money.zero())
        current_by_asset_class: dict[AssetClass, Money] = {}
        for account_id, balance in balances.items():
            asset_class = asset_class_by_account_id.get(account_id)
            if asset_class is not None:
                current_by_asset_class[asset_class] = current_by_asset_class.get(asset_class, Money.zero()) + balance

        for asset_class, weight in target_weights.items():
            if remaining_net == Money.zero():
                break
            target_value = Money.of(total_value.amount * weight.value)
            current_value = current_by_asset_class.get(asset_class, Money.zero())
            if current_value <= target_value:
                continue
            excess = current_value - target_value
            local_remaining = excess if excess < remaining_net else remaining_net
            candidates = sorted(
                (a for a in accounts_by_asset_class.get(asset_class, []) if _is_eligible(a.account_type)),
                key=lambda a: order_index.get(a.account_type, len(order_index)),
            )
            for account in candidates:
                if local_remaining == Money.zero():
                    break
                local_remaining = local_remaining - _sell(account, local_remaining)

    for account_type in withdrawal_strategy.order:
        if remaining_net == Money.zero():
            break
        if not _is_eligible(account_type):
            continue
        for account in accounts_by_type.get(account_type, []):
            if remaining_net == Money.zero():
                break
            _sell(account, remaining_net)

    return WithdrawalOutcome(
        withdrawals=withdrawals,
        updated_cost_basis=updated_cost_basis,
        capital_gains_tax=total_capital_gains_tax,
        remaining_shortfall=remaining_net,
        withdrawals_by_asset_class=withdrawals_by_asset_class,
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
