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
