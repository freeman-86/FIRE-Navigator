from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.domain.value_objects import Money


class AccountType(str, Enum):
    NISA_GROWTH = "nisa_growth"
    NISA_TSUMITATE = "nisa_tsumitate"
    IDECO = "ideco"
    COMPANY_DC = "company_dc"
    ZAIKEI = "zaikei"
    TAXABLE = "taxable"
    CASH = "cash"


@dataclass
class Account:
    """Plan Aggregateに属する口座の識別情報。保有資産(Portfolio)は独立したAggregateであり、
    account_idを共通キーとして参照する（オブジェクトとして直接埋め込まない）。
    """

    account_id: str
    account_type: AccountType
    monthly_contribution: Optional[Money] = None
