from core.domain.market_data import AnnualReturnSeries, HistoricalDataset
from core.domain.value_objects import Rate


def small_dataset() -> HistoricalDataset:
    """テスト用の小さな過去データセット（4年分、2資産クラス）。相関・平均・標準偏差を手計算しやすい値。"""

    domestic_equity = AnnualReturnSeries(
        asset_class="domestic_equity",
        source="test",
        verified=True,
        returns_by_year={2001: Rate.of("0.10"), 2002: Rate.of("-0.10"), 2003: Rate.of("0.20"), 2004: Rate.of("0.00")},
    )
    domestic_bond = AnnualReturnSeries(
        asset_class="domestic_bond",
        source="test",
        verified=False,
        returns_by_year={2001: Rate.of("0.02"), 2002: Rate.of("0.01"), 2003: Rate.of("0.03"), 2004: Rate.of("0.00")},
    )
    return HistoricalDataset(
        start_year=2001,
        end_year=2004,
        series_by_asset_class={
            "domestic_equity": domestic_equity,
            "domestic_bond": domestic_bond,
        },
    )
