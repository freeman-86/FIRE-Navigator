from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects import EventCondition, Money


@dataclass
class OneTimeExpense:
    """車・旅行・住宅購入等、特定の年月に一度だけ発生する単発支出（ギャップ分析3.3）。

    triggerで指定した年月にamount全額が一括で計上される（Expenseのような毎月発生・
    行ごとのgrowth_rateは持たない）。amountは「プラン開始時点（今日）の価値」として入力する
    前提で、発生年まではプラン共通のインフレ率で複利計算してから計上される
    （core/simulation/projection/projection_engine.py の_one_time_expenses_by_month_offset）。
    """

    expense_id: str
    category: str
    amount: Money
    trigger: EventCondition
