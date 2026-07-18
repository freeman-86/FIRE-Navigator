from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml

from core.domain.asset import AssetClass
from core.domain.market_data import AnnualReturnSeries, HistoricalDataset
from core.domain.value_objects import Rate

DEFAULT_HISTORICAL_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "market_data" / "historical_returns_2001_2024.yaml"
)


def load_historical_dataset(
    config_path: Union[str, Path] = DEFAULT_HISTORICAL_DATASET_PATH,
) -> HistoricalDataset:
    """historical_returns.yamlを読み込み、資産クラス別の年次リターン系列をHistoricalDatasetとして返す。

    yaml読込を行うのはこの関数のみ。core/simulation側はyamlを直接読まず、
    ここで変換済みのHistoricalDatasetを受け取るだけにする（設計書3.2 依存方向の原則）。
    """

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    series_by_asset_class = {}
    for asset_class_key, entry in raw["asset_classes"].items():
        asset_class = AssetClass(asset_class_key)
        series_by_asset_class[asset_class] = AnnualReturnSeries(
            asset_class=asset_class,
            source=str(entry["source"]),
            verified=bool(entry["verified"]),
            returns_by_year={
                int(year): Rate.of(value) for year, value in entry["annual_returns"].items()
            },
        )

    return HistoricalDataset(
        start_year=int(raw["start_year"]),
        end_year=int(raw["end_year"]),
        series_by_asset_class=series_by_asset_class,
    )
