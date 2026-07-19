from __future__ import annotations

from dataclasses import dataclass

from core.domain.asset import Asset
from core.domain.value_objects import Money


@dataclass
class Holding:
    """asset 1件分の保有情報。current_value（現在の評価額）とcost_basis（取得原価）を
    分けて持つことで、シミュレーション開始時点で既に含み益/含み損がある状態を表現できる
    （両者が同額なら含み益ゼロからのスタート）。譲渡税計算は取り崩し時にcost_basisを基準に行う。
    """

    asset: Asset
    quantity: float
    current_value: Money
    cost_basis: Money

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("quantity は負の値にできません")
