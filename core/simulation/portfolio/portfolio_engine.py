from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from core.domain.account import Account, AccountType
from core.domain.asset import AssetClass
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.portfolio_rules import PortfolioRules
from core.domain.value_objects import Money, Rate
from core.simulation.portfolio.account_rules import cap_contribution

TAX_DEDUCTIBLE_ACCOUNT_TYPES = (AccountType.IDECO, AccountType.COMPANY_DC)


@dataclass
class FixedContributionPlan:
    """Account.monthly_contributionで確定している、その年の拠出計画（拠出上限内に切り詰め済み）。"""

    contributions: dict[str, Money] = field(default_factory=dict)
    tax_deductible_amount: Money = field(default_factory=Money.zero)


def plan_fixed_contributions(
    accounts: list[Account],
    lifetime_contributions: dict[str, Money],
    portfolio_rules: PortfolioRules,
) -> FixedContributionPlan:
    contributions: dict[str, Money] = {}
    tax_deductible_amount = Money.zero()

    for account in accounts:
        if account.monthly_contribution is None:
            continue

        desired = account.monthly_contribution * 12
        rules = portfolio_rules.rules_for(account.account_type)
        capped = cap_contribution(
            desired,
            rules,
            contributed_this_year=Money.zero(),
            lifetime_contributed=lifetime_contributions.get(account.account_id, Money.zero()),
        )
        if capped == Money.zero():
            continue

        contributions[account.account_id] = capped
        if account.account_type in TAX_DEDUCTIBLE_ACCOUNT_TYPES:
            tax_deductible_amount = tax_deductible_amount + capped

    return FixedContributionPlan(contributions=contributions, tax_deductible_amount=tax_deductible_amount)


def allocate_discretionary_surplus(
    accounts: list[Account],
    account_balances: dict[str, Money],
    lifetime_contributions: dict[str, Money],
    already_contributed_this_year: dict[str, Money],
    surplus: Money,
    contribution_strategy: ContributionStrategy,
    portfolio_rules: PortfolioRules,
    asset_class_by_account_id: Optional[dict[str, AssetClass]] = None,
    target_weights: Optional[dict[AssetClass, Rate]] = None,
) -> tuple[dict[str, Money], Money]:
    """裁量的余剰(surplus)をcontribution_strategy.orderの優先順位で口座へ配分する。

    戻り値は (口座ごとの追加拠出額, 配分しきれなかった残り)。
    CASHは口座残高がemergency_fund_targetに達するまでを上限として扱う（拠出限度額の概念とは別）。

    asset_class_by_account_id/target_weightsが両方指定されている場合（AllocationPolicyが
    設定されているPlan）、CASH以外の口座はcontribution_strategy.orderの固定順ではなく、
    現在最も過小配分な資産クラスの口座を優先する（ギャップ分析3.7「新規拠出を優先」したリバランス）。
    どちらか片方でも省略時は従来通りcontribution_strategy.orderの固定順で配分する。
    """

    remaining = surplus if not surplus.is_negative else Money.zero()
    additional_contributions: dict[str, Money] = {}

    accounts_by_type: dict[AccountType, list[Account]] = {}
    for account in accounts:
        accounts_by_type.setdefault(account.account_type, []).append(account)

    if AccountType.CASH in contribution_strategy.order:
        for account in accounts_by_type.get(AccountType.CASH, []):
            if remaining == Money.zero():
                break
            current_balance = account_balances.get(account.account_id, Money.zero())
            gap = contribution_strategy.emergency_fund_target - current_balance
            if gap.is_negative or gap == Money.zero():
                continue
            take = gap if gap < remaining else remaining
            additional_contributions[account.account_id] = (
                additional_contributions.get(account.account_id, Money.zero()) + take
            )
            remaining = remaining - take

    candidate_accounts: list[Account] = []
    for account_type in contribution_strategy.order:
        if account_type == AccountType.CASH:
            continue
        candidate_accounts.extend(accounts_by_type.get(account_type, []))

    if target_weights and asset_class_by_account_id:
        candidate_accounts = _sort_by_drift(candidate_accounts, account_balances, asset_class_by_account_id, target_weights)

    for account in candidate_accounts:
        if remaining == Money.zero():
            break
        rules = portfolio_rules.rules_for(account.account_type)
        already_contributed = already_contributed_this_year.get(
            account.account_id, Money.zero()
        ) + additional_contributions.get(account.account_id, Money.zero())
        take = cap_contribution(
            remaining,
            rules,
            contributed_this_year=already_contributed,
            lifetime_contributed=lifetime_contributions.get(account.account_id, Money.zero()),
        )
        if take == Money.zero():
            continue
        additional_contributions[account.account_id] = (
            additional_contributions.get(account.account_id, Money.zero()) + take
        )
        remaining = remaining - take

    return additional_contributions, remaining


def _sort_by_drift(
    candidate_accounts: list[Account],
    account_balances: dict[str, Money],
    asset_class_by_account_id: dict[str, AssetClass],
    target_weights: dict[AssetClass, Rate],
) -> list[Account]:
    """資産クラスの目標比率に対する現在の乖離(目標額-現在額)が大きい口座ほど先に来るよう並べ替える。

    対象の資産クラスがtarget_weightsに含まれない口座は乖離0扱いとし、Pythonのsortが安定ソートで
    あることを利用して元のcontribution_strategy.order通りの相対順を保つ。
    """

    total_value = sum(account_balances.values(), Money.zero()).amount
    current_by_asset_class: dict[AssetClass, Decimal] = {}
    for account_id, balance in account_balances.items():
        asset_class = asset_class_by_account_id.get(account_id)
        if asset_class is None:
            continue
        current_by_asset_class[asset_class] = current_by_asset_class.get(asset_class, Decimal(0)) + balance.amount

    def drift_for(account: Account) -> Decimal:
        asset_class = asset_class_by_account_id.get(account.account_id)
        if asset_class is None or asset_class not in target_weights:
            return Decimal(0)
        target_value = total_value * target_weights[asset_class].value
        current_value = current_by_asset_class.get(asset_class, Decimal(0))
        return target_value - current_value

    return sorted(candidate_accounts, key=drift_for, reverse=True)
