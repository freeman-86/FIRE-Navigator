from __future__ import annotations

from datetime import date
from typing import Optional

from core.domain.value_objects import EventCondition, EventConditionType


def resolve_condition_year(condition: EventCondition, start_year: int, birth_date: date) -> Optional[int]:
    """age/date系の条件が指す西暦年を解決する。networth_multiple_of_expense等、
    年次シミュレーション結果に照らさないと判定できない条件はNoneを返す。
    """

    if condition.condition_type == EventConditionType.PLAN_START:
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

    if condition.condition_type == EventConditionType.PLAN_START:
        return start_year, start_month
    if condition.condition_type in (EventConditionType.DATE, EventConditionType.FIXED_DATE):
        return condition.date.year, condition.date.month
    if condition.condition_type == EventConditionType.AGE:
        return _age_reached_month(birth_date, condition.age)
    return None


def _age_reached_month(birth_date: date, age: int) -> tuple[int, int]:
    """その年齢に達する最初の（月の1日時点でその年齢だとage_at()が判定する）西暦年・月を返す。

    age_at()は「その月の1日時点で誕生日を迎えているか」で年齢を判定するため、誕生日が月の
    2日以降（birth_date.day > 1）の場合、誕生月の1日はまだ誕生日前で年齢表示は1つ若いままになる
    （実際にその年齢になったと表示されるのは翌月から）。ここでもage_at()と同じ基準に揃えることで、
    単発支出等の発生月と年齢表示(age_self)がズレないようにする。
    """

    target_year = birth_date.year + age
    if birth_date.day == 1:
        return target_year, birth_date.month
    target_month = birth_date.month + 1
    if target_month > 12:
        return target_year + 1, 1
    return target_year, target_month
