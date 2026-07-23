from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects import Rate

# 資産クラスの識別子（例: "equity_sp500", "bond_us_treasury", "btc"）。
# 固定Enumではなく単なる文字列とし、有効な値の集合はconfig/asset_classes.yaml
# （repositories/asset_class_repository.pyが読み込む）で管理する。domain層は
# I/Oを持たないため、値の妥当性検証はadapters/sheets側の責務とする（設計書3.2）。
AssetClass = str


@dataclass
class Asset:
    asset_class: AssetClass
    expected_return: Rate
