from __future__ import annotations

from core.domain.market_data import HistoricalDataset


def generate_windows(dataset: HistoricalDataset, window_length: int) -> list[int]:
    """過去データセットから、開始年をずらしたwindow_length年分の窓の開始年一覧を返す。

    例: dataset が2001〜2024年、window_length=20なら、2001年開始〜2005年開始の5つの窓を返す
    （2005年開始+20年-1=2024年で収まる最後の窓）。
    """

    last_start_year = dataset.end_year - window_length + 1
    if last_start_year < dataset.start_year:
        return []
    return list(range(dataset.start_year, last_start_year + 1))
