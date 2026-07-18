from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.domain.portfolio import Portfolio
from core.domain.value_objects import Money


class AccountType(str, Enum):
    NISA_GROWTH = "nisa_growth"
    NISA_TSUMITATE = "nisa_tsumitate"
    IDECO = "ideco"
    COMPANY_DC = "company_dc"
    ZAIKEI = "zaikei"
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
    monthly_contribution: Optional[Money] = None
