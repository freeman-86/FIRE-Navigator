from __future__ import annotations

from core.domain.asset import AssetClass
from core.domain.market_data import HistoricalDataset
from core.domain.value_objects import Rate


def build_return_series(
    dataset: HistoricalDataset, window_start_year: int, window_length: int
) -> dict[AssetClass, list[Rate]]:
    """指定した窓（window_start_yearからwindow_length年分）の資産クラスごとのリターン系列を切り出す。"""

    result: dict[AssetClass, list[Rate]] = {}
    for asset_class, series in dataset.series_by_asset_class.items():
        result[asset_class] = [series.returns_by_year[window_start_year + i] for i in range(window_length)]
    return result
