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
