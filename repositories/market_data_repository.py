from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml

from core.domain.asset import AssetClass
from core.domain.market_data import AnnualReturnSeries, HistoricalDataset
from core.domain.value_objects import Rate
from repositories.asset_class_repository import DEFAULT_ASSET_CLASSES_PATH

DEFAULT_HISTORICAL_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "market_data" / "historical_returns_1928_2024.yaml"
)


def load_historical_dataset(
    config_path: Union[str, Path] = DEFAULT_HISTORICAL_DATASET_PATH,
    asset_classes_config_path: Union[str, Path] = DEFAULT_ASSET_CLASSES_PATH,
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

    _apply_historical_proxies(series_by_asset_class, asset_classes_config_path)

    return HistoricalDataset(
        start_year=int(raw["start_year"]),
        end_year=int(raw["end_year"]),
        series_by_asset_class=series_by_asset_class,
    )


def _apply_historical_proxies(
    series_by_asset_class: dict[AssetClass, AnnualReturnSeries],
    asset_classes_config_path: Union[str, Path],
) -> None:
    """信頼できる長期の過去データが無い資産クラス（例: BTC）向けに、config/asset_classes.yaml の
    historical_proxy設定を見て、代用元の資産クラスの系列をそのままコピーしたエイリアスを追加する
    （series_by_asset_classを直接書き換える）。

    これにより、モンテカルロEngineの分布推定・相関計算・加重合成、ヒストリカルEngineのバックテストの
    いずれも、その資産クラス独自の実データが無いために加重合成からまるごと除外され実質0%リターン
    扱いになる（＝配分比率のその分が欠落したまま計算される）状態を避けられる。asset_class自体
    （取り崩し優先順位・月次詳細の内訳・資産配分表示等）には一切影響しない、モンテカルロ/
    ヒストリカルの計算だけに閉じた変更。
    """

    with open(asset_classes_config_path, encoding="utf-8") as f:
        asset_classes_raw = yaml.safe_load(f)

    for asset_class_key, entry in asset_classes_raw["asset_classes"].items():
        proxy_key = entry.get("historical_proxy")
        if not proxy_key:
            continue
        asset_class = AssetClass(asset_class_key)
        if asset_class in series_by_asset_class:
            continue  # 既に実データがあるならそちらを優先し、代用しない
        proxy_series = series_by_asset_class.get(AssetClass(proxy_key))
        if proxy_series is None:
            continue  # 代用先の系列も存在しない場合は何もしない（従来通り0%リターン扱いのまま）
        series_by_asset_class[asset_class] = AnnualReturnSeries(
            asset_class=asset_class,
            source=f"{proxy_series.source}（{asset_class_key}の長期データが無いため代用。実データではない）",
            verified=False,
            returns_by_year=dict(proxy_series.returns_by_year),
        )
