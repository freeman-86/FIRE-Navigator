from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.asset import AssetClass
from core.domain.value_objects import Rate


@dataclass
class AnnualReturnSeries:
    asset_class: AssetClass
    source: str
    verified: bool
    returns_by_year: dict[int, Rate] = field(default_factory=dict)


@dataclass
class HistoricalDataset:
    start_year: int
    end_year: int
    series_by_asset_class: dict[AssetClass, AnnualReturnSeries] = field(default_factory=dict)


def filter_from_year(dataset: HistoricalDataset, start_year: int) -> HistoricalDataset:
    """指定した年以降のデータだけに絞り込んだHistoricalDatasetを返す（元のデータセットは変更しない）。

    Monte Carlo Engineの分布・相関推定を特定の期間だけに限定したい場合
    （例: 金本位制終了(1971年)以降のデータだけで推定し直す参考値）に使う。
    """

    filtered_series = {
        asset_class: AnnualReturnSeries(
            asset_class=series.asset_class,
            source=series.source,
            verified=series.verified,
            returns_by_year={year: rate for year, rate in series.returns_by_year.items() if year >= start_year},
        )
        for asset_class, series in dataset.series_by_asset_class.items()
    }
    return HistoricalDataset(start_year=start_year, end_year=dataset.end_year, series_by_asset_class=filtered_series)
