from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects import Money


@dataclass
class ProgressRecord:
    """ある年の実績ネットワース（Excelやスプレッドシートから手入力される実績値）。"""

    year: int
    actual_networth: Money
