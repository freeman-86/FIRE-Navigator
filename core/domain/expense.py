from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.domain.value_objects import EventCondition, Money, Rate


@dataclass
class Expense:
    """経常支出。start_condition/end_conditionは任意（両方省略した場合はプラン全期間で発生する）。
    同じ支出が途中で金額・成長率ごと変わるケース（住宅ローン完済後の生活費増減等）は、
    start_condition/end_conditionをずらした複数行に分けることで表現する（Incomeと同じ設計）。
    """

    expense_id: str
    category: str
    amount: Money
    growth_rate: Rate
    start_condition: Optional[EventCondition] = None
    end_condition: Optional[EventCondition] = None
