from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.domain.account import AccountType
from core.domain.value_objects import Money


@dataclass
class AccountRules:
    annual_limit: Optional[Money]
    lifetime_limit: Optional[Money]
    tax_free: bool


@dataclass
class PortfolioRules:
    rules_by_account_type: dict[AccountType, AccountRules] = field(default_factory=dict)

    def rules_for(self, account_type: AccountType) -> AccountRules:
        return self.rules_by_account_type.get(
            account_type, AccountRules(annual_limit=None, lifetime_limit=None, tax_free=False)
        )
