from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects import Money


@dataclass
class EducationExpenseBand:
    """特定の子供が指定の年齢帯にいる間、毎月発生する教育費（小学校・塾・中学・高校・大学等）。

    同じ子供に複数のBandが同時に該当してもよい（例: 小学校＋塾を並行して計上）。
    end_ageは含む（start_age <= 年齢 <= end_ageの間、毎月monthly_amountが発生する）。
    """

    band_id: str
    child_id: str
    category: str
    start_age: int
    end_age: int
    monthly_amount: Money

    def __post_init__(self) -> None:
        if self.end_age < self.start_age:
            raise ValueError("end_age は start_age 以上である必要があります")

    def applies_to_age(self, age: int) -> bool:
        return self.start_age <= age <= self.end_age
