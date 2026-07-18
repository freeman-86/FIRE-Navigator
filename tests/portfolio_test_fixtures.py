from core.domain.contribution_strategy import ContributionStrategy
from core.domain.portfolio_rules import PortfolioRules


def no_allocation_contribution_strategy() -> ContributionStrategy:
    """裁量的余剰を口座へ配分せず、これまで通りunallocated_surplusへ積み上げるだけにするテスト用フィクスチャ。"""

    return ContributionStrategy(order=[])


def empty_portfolio_rules() -> PortfolioRules:
    return PortfolioRules()
