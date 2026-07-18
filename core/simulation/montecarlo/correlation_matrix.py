from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.asset import AssetClass
from core.domain.market_data import HistoricalDataset


@dataclass
class CorrelationMatrix:
    correlations: dict[tuple[AssetClass, AssetClass], float] = field(default_factory=dict)

    def get(self, a: AssetClass, b: AssetClass) -> float:
        if a == b:
            return 1.0
        return self.correlations.get((a, b), self.correlations.get((b, a), 0.0))


def compute_correlation_matrix(dataset: HistoricalDataset) -> CorrelationMatrix:
    """過去データセットの年次リターン系列から資産クラス間のピアソン相関係数を算出する。"""

    asset_classes = list(dataset.series_by_asset_class.keys())
    correlations: dict[tuple[AssetClass, AssetClass], float] = {}
    for i, a in enumerate(asset_classes):
        for b in asset_classes[i + 1 :]:
            years = sorted(
                set(dataset.series_by_asset_class[a].returns_by_year)
                & set(dataset.series_by_asset_class[b].returns_by_year)
            )
            x = [float(dataset.series_by_asset_class[a].returns_by_year[year].value) for year in years]
            y = [float(dataset.series_by_asset_class[b].returns_by_year[year].value) for year in years]
            correlations[(a, b)] = _pearson_correlation(x, y)

    return CorrelationMatrix(correlations)


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    covariance = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    variance_x = sum((v - mean_x) ** 2 for v in x)
    variance_y = sum((v - mean_y) ** 2 for v in y)
    denominator = (variance_x * variance_y) ** 0.5
    return covariance / denominator if denominator != 0 else 0.0
