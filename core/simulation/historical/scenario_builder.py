from __future__ import annotations

from decimal import Decimal
from typing import Callable

from core.domain.asset import AssetClass
from core.domain.value_objects import Rate


def build_growth_rate_provider(
    return_series: dict[AssetClass, list[Rate]],
    weight_lookup: Callable[[int], dict[AssetClass, Decimal]],
) -> Callable[[int], Rate]:
    """資産クラスごとの年次リターン系列を、weight_lookupが返す配分比率で加重した成長率へ変換し、
    Projection Engineが受け取れるgrowth_rate_provider関数として返す。

    weight_lookupは月次オフセットを受け取り、その時点の資産クラス別配分比率を返す関数
    （core.simulation.montecarlo.montecarlo_engine.build_weight_lookup()と共通の形。
    AllocationPolicyが設定されたPlanでは年齢とともに比率が変わるため、事前に単一の系列へ
    固定合成せず、呼び出しの都度その時点の比率で合成する。設計書v1.1⑦、ギャップ分析3.7
    「モンテカルロエンジンへの反映」はHistorical Engineにも同様に適用する）。

    実際の過去データは年次でしか持たないため、月次呼び出しは12回ごとに同じ年の値を使い回し、
    年率をmonthly_equivalent()で月率に変換して返す（月内の値動きは一定と仮定する近似。実際の
    月次指数データへの置き換えは将来課題）。

    Projection Engineの計算期間が窓の長さ(window_length)を超える場合は、窓を先頭から
    繰り返し再生する（実績データが尽きても計算を継続できるようにするための単純化）。
    """

    window_length = len(next(iter(return_series.values()))) if return_series else 0

    def provider(month_offset: int) -> Rate:
        if window_length == 0:
            return Rate.zero()
        year_offset = (month_offset // 12) % window_length
        weights = weight_lookup(month_offset)
        asset_classes = [ac for ac in return_series if ac in weights]
        blended = sum((return_series[ac][year_offset].value * weights[ac] for ac in asset_classes), Decimal(0))
        return Rate(blended).monthly_equivalent()

    return provider
