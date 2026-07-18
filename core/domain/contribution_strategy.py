from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.account import AccountType
from core.domain.value_objects import Money


@dataclass
class ContributionStrategy:
    """余剰資金を口座へ振り分ける優先順位（例:緊急資金→NISA→iDeCo→課税口座）。

    退職後の取り崩し順序を表すWithdrawalStrategyとは別概念（積立期の拠出優先順位）。
    """

    order: list[AccountType]
    emergency_fund_target: Money = field(default_factory=Money.zero)
