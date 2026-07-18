from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.domain.portfolio import Portfolio


class AccountType(str, Enum):
    NISA_GROWTH = "nisa_growth"
    NISA_TSUMITATE = "nisa_tsumitate"
    IDECO = "ideco"
    TAXABLE = "taxable"
    CASH = "cash"


class OwnerType(str, Enum):
    SELF = "self"
    SPOUSE = "spouse"
    JOINT = "joint"


@dataclass
class Account:
    account_id: str
    account_type: AccountType
    owner: OwnerType
    portfolio: Portfolio
