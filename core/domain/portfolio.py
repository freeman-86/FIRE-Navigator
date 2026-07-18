from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.domain.asset import AssetClass
from core.domain.holding import Holding
from core.domain.value_objects import Rate


@dataclass
class AllocationPolicy:
    target_weights: dict[AssetClass, Rate] = field(default_factory=dict)


@dataclass
class Portfolio:
    holdings: list[Holding] = field(default_factory=list)
    allocation_policy: Optional[AllocationPolicy] = None
