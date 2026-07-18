from __future__ import annotations

from dataclasses import dataclass

from core.domain.asset import Asset
from core.domain.value_objects import Money


@dataclass
class Holding:
    asset: Asset
    quantity: float
    cost_basis: Money

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("quantity は負の値にできません")
