from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml

from core.domain.asset import AssetClass

DEFAULT_ASSET_CLASSES_PATH = Path(__file__).resolve().parent.parent / "config" / "asset_classes.yaml"


def load_asset_class_registry(
    config_path: Union[str, Path] = DEFAULT_ASSET_CLASSES_PATH,
) -> dict[AssetClass, str]:
    """asset_classes.yamlを読み込み、資産クラス識別子→日本語表示名のdictを返す。

    有効な資産クラスの集合はこのファイル経由でのみ得られる（設計書3.2 依存方向の原則。
    core/simulation側はyamlを直接読まない）。adapters層はこの戻り値を使って
    入力値の妥当性検証・エラーメッセージ生成を行う。
    """

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return {code: entry["display_name"] for code, entry in raw["asset_classes"].items()}
