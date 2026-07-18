from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.domain.account import AccountType


@dataclass
class WithdrawalRule:
    rule_type: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class WithdrawalStrategy:
    order: list[AccountType]
    rules: list[WithdrawalRule] = field(default_factory=list)
