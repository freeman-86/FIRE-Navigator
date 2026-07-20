from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.account import Account
from core.domain.asset import AssetClass
from core.domain.plan import Plan
from core.domain.portfolio_rules import PortfolioRules
from core.domain.tax_config import CapitalGainsTaxRules
from core.domain.value_objects import Money, Rate
from core.simulation.withdrawal.withdrawal_engine import (
    reduce_cost_basis_proportionally,
    withdraw_from_single_account,
)


@dataclass
class RebalanceOutcome:
    account_balances: dict[str, Money] = field(default_factory=dict)
    cost_basis_balances: dict[str, Money] = field(default_factory=dict)
    lifetime_contributions: dict[str, Money] = field(default_factory=dict)
    capital_gains_tax: Money = field(default_factory=Money.zero)
    unreinvested_proceeds: Money = field(default_factory=Money.zero)


def rebalance(
    plan: Plan,
    account_balances: dict[str, Money],
    cost_basis_balances: dict[str, Money],
    lifetime_contributions: dict[str, Money],
    asset_class_by_account_id: dict[str, AssetClass],
    target_weights: dict[AssetClass, Rate],
    portfolio_rules: PortfolioRules,
    capital_gains_tax_rules: CapitalGainsTaxRules,
    age: int,
) -> RebalanceOutcome:
    """新規拠出（allocate_discretionary_surplusのドリフト考慮配分）で埋めきれなかった資産クラスの
    乖離のうち、過大な資産クラスを目標比率まで売却することで解消する（ギャップ分析3.7
    「新規拠出を優先、不足分のみ売却」の売却ステップ）。売却代金の買い直しは行わず、すべて
    unreinvested_proceedsとして返す（呼び出し元でsurplus_reserveに合算される）。将来の新規拠出は
    allocate_discretionary_surplusの目標比率配分ロジックでそのまま反映されるため、買い直しの
    処理がなくても長期的には目標配分に近づく。

    売却口座の優先順位は通常の取り崩し(withdraw_shortfall)と統一し、plan.withdrawal_strategy.order
    の順（課税口座を先に、非課税口座を後に）に売却する。ageがportfolio_rulesのmin_withdrawal_age
    未満の口座タイプ（iDeCo/企業型DC等）はそもそも売却対象から除外し、他の口座で賄う
    （withdraw_shortfallと同様、口座を強制的に売却することはしない）。target_weightsが空の場合は
    何もしない（AllocationPolicy未設定のPlanとの後方互換性）。
    """

    if not target_weights:
        return RebalanceOutcome(account_balances, cost_basis_balances, lifetime_contributions, Money.zero())

    total_value = sum(account_balances.values(), Money.zero())
    if total_value == Money.zero():
        return RebalanceOutcome(account_balances, cost_basis_balances, lifetime_contributions, Money.zero())

    current_by_asset_class: dict[AssetClass, Money] = {}
    for account_id, balance in account_balances.items():
        asset_class = asset_class_by_account_id.get(account_id)
        if asset_class is not None:
            current_by_asset_class[asset_class] = current_by_asset_class.get(asset_class, Money.zero()) + balance

    drift_by_asset_class: dict[AssetClass, Money] = {
        asset_class: Money.of(total_value.amount * weight.value) - current_by_asset_class.get(asset_class, Money.zero())
        for asset_class, weight in target_weights.items()
    }

    accounts_by_asset_class: dict[AssetClass, list[Account]] = {}
    for account in plan.accounts:
        asset_class = asset_class_by_account_id.get(account.account_id)
        if asset_class is not None:
            accounts_by_asset_class.setdefault(asset_class, []).append(account)

    order_index = {account_type: index for index, account_type in enumerate(plan.withdrawal_strategy.order)}

    balances = dict(account_balances)
    cost_basis = dict(cost_basis_balances)
    total_tax = Money.zero()
    proceeds = Money.zero()

    for asset_class, drift in drift_by_asset_class.items():
        if not drift.is_negative:
            continue
        excess = -drift
        eligible = [
            account
            for account in accounts_by_asset_class.get(asset_class, [])
            if _is_withdrawal_eligible(account, portfolio_rules, age)
        ]
        candidates = sorted(eligible, key=lambda a: order_index.get(a.account_type, len(order_index)))
        for account in candidates:
            if excess == Money.zero():
                break
            available = balances.get(account.account_id, Money.zero())
            if available == Money.zero():
                continue
            is_taxable = not portfolio_rules.rules_for(account.account_type).tax_free
            take_gross, take_net, tax = withdraw_from_single_account(
                available, cost_basis.get(account.account_id, Money.zero()), excess, is_taxable,
                capital_gains_tax_rules.rate,
            )
            if take_gross == Money.zero():
                continue
            cost_basis[account.account_id] = reduce_cost_basis_proportionally(
                cost_basis.get(account.account_id, Money.zero()), available, take_gross
            )
            balances[account.account_id] = available - take_gross
            total_tax = total_tax + tax
            proceeds = proceeds + take_net
            excess = excess - take_net

    return RebalanceOutcome(
        account_balances=balances,
        cost_basis_balances=cost_basis,
        lifetime_contributions=lifetime_contributions,
        capital_gains_tax=total_tax,
        unreinvested_proceeds=proceeds,
    )


def _is_withdrawal_eligible(account: Account, portfolio_rules: PortfolioRules, age: int) -> bool:
    min_withdrawal_age = portfolio_rules.rules_for(account.account_type).min_withdrawal_age
    return min_withdrawal_age is None or age >= min_withdrawal_age
