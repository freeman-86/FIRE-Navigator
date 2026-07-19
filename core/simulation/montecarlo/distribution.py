from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.domain.asset import AssetClass
from core.domain.market_data import HistoricalDataset
from core.domain.value_objects import Rate

MONTHS_PER_YEAR = 12
_SQRT_MONTHS_PER_YEAR = Decimal(MONTHS_PER_YEAR).sqrt()


@dataclass
class AssetReturnDistribution:
    asset_class: AssetClass
    mean: Rate
    std_dev: Rate


def to_monthly_distributions(
    distributions: dict[AssetClass, AssetReturnDistribution],
) -> dict[AssetClass, AssetReturnDistribution]:
    """年率で表された分布パラメータを、独立同分布の月次リターンを仮定して月率へ変換する
    （mean/12, std_dev/sqrt(12)という標準的な近似）。Monte Carlo Engineが毎月サンプリングする際に使う。
    """

    return {
        asset_class: AssetReturnDistribution(
            asset_class=asset_class,
            mean=Rate(distribution.mean.value / MONTHS_PER_YEAR),
            std_dev=Rate(distribution.std_dev.value / _SQRT_MONTHS_PER_YEAR),
        )
        for asset_class, distribution in distributions.items()
    }


def distributions_from_historical_dataset(dataset: HistoricalDataset) -> dict[AssetClass, AssetReturnDistribution]:
    """各資産クラスの年次リターン系列から標本平均・標本標準偏差を算出し、正規分布のパラメータとする。"""

    result: dict[AssetClass, AssetReturnDistribution] = {}
    for asset_class, series in dataset.series_by_asset_class.items():
        values = [r.value for r in series.returns_by_year.values()]
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else Decimal(0)
        result[asset_class] = AssetReturnDistribution(
            asset_class=asset_class,
            mean=Rate(mean),
            std_dev=Rate(variance.sqrt()),
        )
    return result
