from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.account import Account, AccountType
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.portfolio_rules import PortfolioRules
from core.domain.value_objects import Money
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
) -> tuple[dict[str, Money], Money]:
    """裁量的余剰(surplus)をcontribution_strategy.orderの優先順位で口座へ配分する。

    戻り値は (口座ごとの追加拠出額, 配分しきれなかった残り)。
    CASHは口座残高がemergency_fund_targetに達するまでを上限として扱う（拠出限度額の概念とは別）。
    """

    remaining = surplus if not surplus.is_negative else Money.zero()
    additional_contributions: dict[str, Money] = {}

    accounts_by_type: dict[AccountType, list[Account]] = {}
    for account in accounts:
        accounts_by_type.setdefault(account.account_type, []).append(account)

    for account_type in contribution_strategy.order:
        if remaining == Money.zero():
            break

        if account_type == AccountType.CASH:
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
            continue

        rules = portfolio_rules.rules_for(account_type)
        for account in accounts_by_type.get(account_type, []):
            if remaining == Money.zero():
                break
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
