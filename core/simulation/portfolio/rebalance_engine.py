from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.account import Account
from core.domain.asset import AssetClass
from core.domain.plan import Plan
from core.domain.portfolio_rules import PortfolioRules
from core.domain.tax_config import CapitalGainsTaxRules
from core.domain.value_objects import Money, Rate
from core.simulation.portfolio.account_rules import cap_contribution
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
) -> RebalanceOutcome:
    """新規拠出（allocate_discretionary_surplusのドリフト考慮配分）で埋めきれなかった資産クラスの
    乖離を、過大な口座から売却し過小な口座へ再投資することで解消する（ギャップ分析3.7
    「新規拠出を優先、不足分のみ売却」の売却ステップ）。

    売却は非課税口座（NISA等）を優先し、それでも足りない場合のみ課税口座（TAXABLE）から売却する
    （譲渡税の発生を最小化するため）。再投資は各口座のcap_contributionルール（年間/生涯枠）を
    尊重する。ただし年間枠については、同じ月に発生する通常の拠出フローとは独立に判定する簡易化
    （両者を跨いだ年間枠の厳密な合算管理はしない）。target_weightsが空の場合は何もしない
    （AllocationPolicy未設定のPlanとの後方互換性）。
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

    balances = dict(account_balances)
    cost_basis = dict(cost_basis_balances)
    lifetime = dict(lifetime_contributions)
    total_tax = Money.zero()
    proceeds = Money.zero()

    for asset_class, drift in drift_by_asset_class.items():
        if not drift.is_negative:
            continue
        excess = -drift
        candidates = sorted(
            accounts_by_asset_class.get(asset_class, []),
            key=lambda a: not portfolio_rules.rules_for(a.account_type).tax_free,
        )
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

    for asset_class, drift in drift_by_asset_class.items():
        if drift.is_negative or drift == Money.zero() or proceeds == Money.zero():
            continue
        need = drift
        for account in accounts_by_asset_class.get(asset_class, []):
            if need == Money.zero() or proceeds == Money.zero():
                break
            rules = portfolio_rules.rules_for(account.account_type)
            desired = need if need < proceeds else proceeds
            take = cap_contribution(
                desired,
                rules,
                contributed_this_year=Money.zero(),
                lifetime_contributed=lifetime.get(account.account_id, Money.zero()),
            )
            if take == Money.zero():
                continue
            balances[account.account_id] = balances.get(account.account_id, Money.zero()) + take
            cost_basis[account.account_id] = cost_basis.get(account.account_id, Money.zero()) + take
            lifetime[account.account_id] = lifetime.get(account.account_id, Money.zero()) + take
            proceeds = proceeds - take
            need = need - take

    return RebalanceOutcome(
        account_balances=balances,
        cost_basis_balances=cost_basis,
        lifetime_contributions=lifetime,
        capital_gains_tax=total_tax,
        unreinvested_proceeds=proceeds,
    )
