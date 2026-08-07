from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects import EventCondition, Money, Rate


@dataclass
class OneTimeExpense:
    """車・旅行・住宅購入等、特定の年月に一度だけ発生する単発支出（ギャップ分析3.3）。

    triggerで指定した年月にamount全額が一括で計上される（Expenseのような毎月発生はしないが、
    growth_rateはExpenseと同じ意味で持つ）。amountは「プラン開始時点（今日）の価値」として
    入力する前提で、発生年までgrowth_rateで複利計算してから計上される
    （core/simulation/projection/projection_engine.py の_one_time_expenses_by_month_offset）。
    growth_rateが未入力の行はプラン設定のインフレ率を既定値として使う（Expense.growth_rateと
    同じ解決規約、adapters/local/local_data_adapter._parse_growth_rate）。
    """

    expense_id: str
    category: str
    amount: Money
    trigger: EventCondition
    growth_rate: Rate
