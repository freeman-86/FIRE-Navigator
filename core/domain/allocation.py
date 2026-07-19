from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.asset import AssetClass
from core.domain.value_objects import Rate


@dataclass
class AllocationTarget:
    """特定の年齢以降に適用される目標配分比率（資産クラス別）。"""

    age: int
    weights: dict[AssetClass, Rate]


@dataclass
class AllocationPolicy:
    """プラン全体で1つ持つ、年齢別の目標配分比率テーブル（口座横断。ギャップ分析3.7で確定）。

    グライドパスの自動計算式は持たず、ユーザーが年齢ごとに指定したテーブルをそのまま使う
    （ステップ関数として、指定age以上で最も近いTargetを適用する）。
    """

    targets: list[AllocationTarget] = field(default_factory=list)

    def weights_for_age(self, age: int) -> dict[AssetClass, Rate]:
        applicable = [target for target in self.targets if target.age <= age]
        if not applicable:
            return {}
        return max(applicable, key=lambda target: target.age).weights
