from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects import EventCondition, Money


@dataclass
class OneTimeExpense:
    """車・旅行・住宅購入等、特定の年月に一度だけ発生する単発支出（ギャップ分析3.3）。

    triggerで指定した年月にamount全額が一括で計上される（Expenseのような毎月発生・
    growth_rateによる複利成長は持たない）。
    """

    expense_id: str
    category: str
    amount: Money
    trigger: EventCondition
