from __future__ import annotations

from decimal import Decimal
from typing import Callable

from core.domain.asset import AssetClass
from core.domain.value_objects import Rate


def build_growth_rate_provider(
    return_series: dict[AssetClass, list[Rate]],
    asset_class_weights: dict[AssetClass, Decimal],
) -> Callable[[int], Rate]:
    """資産クラスごとの年次リターン系列を、Planの配分比率で加重した単一の年次成長率へ変換し、
    Projection Engineが受け取れるgrowth_rate_provider関数として返す。

    Projection Engineは月次オフセットでこの関数を呼び出す（設計書 Sprint12
    月次化）。実際の過去データは年次でしか持たないため、月次呼び出しは12回ごとに
    同じ年の値を使い回し、年率をmonthly_equivalent()で月率に変換して返す
    （月内の値動きは一定と仮定する近似。実際の月次指数データへの置き換えは将来課題）。

    Projection Engineの計算期間が窓の長さ(window_length)を超える場合は、窓を先頭から
    繰り返し再生する（実績データが尽きても計算を継続できるようにするための単純化）。
    """

    asset_classes = [ac for ac in return_series if ac in asset_class_weights]
    window_length = len(next(iter(return_series.values()))) if return_series else 0

    blended_series: list[Rate] = []
    for offset in range(window_length):
        blended = sum(
            (return_series[ac][offset].value * asset_class_weights[ac] for ac in asset_classes), Decimal(0)
        )
        blended_series.append(Rate(blended))

    def provider(month_offset: int) -> Rate:
        if not blended_series:
            return Rate.zero()
        year_offset = month_offset // 12
        annual_rate = blended_series[year_offset % len(blended_series)]
        return annual_rate.monthly_equivalent()

    return provider
