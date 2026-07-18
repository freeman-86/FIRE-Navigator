from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.domain.value_objects import Rate


class AssetClass(str, Enum):
    DOMESTIC_EQUITY = "domestic_equity"
    GLOBAL_EQUITY = "global_equity"
    DOMESTIC_BOND = "domestic_bond"
    GLOBAL_BOND = "global_bond"
    REIT = "reit"
    GOLD = "gold"
    CASH = "cash"


@dataclass
class Asset:
    asset_class: AssetClass
    expected_return: Rate
    volatility: Rate
