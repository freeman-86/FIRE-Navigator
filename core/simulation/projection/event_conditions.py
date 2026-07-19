from __future__ import annotations

from datetime import date
from typing import Optional

from core.domain.value_objects import EventCondition, EventConditionType


def resolve_condition_year(condition: EventCondition, start_year: int, birth_date: date) -> Optional[int]:
    """age/date系の条件が指す西暦年を解決する。networth_multiple_of_expense等、
    年次シミュレーション結果に照らさないと判定できない条件はNoneを返す。
    """

    if condition.condition_type in (EventConditionType.TODAY, EventConditionType.PLAN_START):
        return start_year
    if condition.condition_type in (EventConditionType.DATE, EventConditionType.FIXED_DATE):
        return condition.date.year
    if condition.condition_type == EventConditionType.AGE:
        return birth_date.year + condition.age
    return None


def resolve_condition_month(
    condition: EventCondition, start_year: int, start_month: int, birth_date: date
) -> Optional[tuple[int, int]]:
    """age/date系の条件が指す(西暦年, 月)を解決する。OneTimeExpense等、発生月ちょうどに
    一括計上したいケースで使う（resolve_condition_yearの月精度版）。
    networth_multiple_of_expense等、年次シミュレーション結果に照らさないと判定できない条件は
    Noneを返す。
    """

    if condition.condition_type in (EventConditionType.TODAY, EventConditionType.PLAN_START):
        return start_year, start_month
    if condition.condition_type in (EventConditionType.DATE, EventConditionType.FIXED_DATE):
        return condition.date.year, condition.date.month
    if condition.condition_type == EventConditionType.AGE:
        return birth_date.year + condition.age, birth_date.month
    return None
