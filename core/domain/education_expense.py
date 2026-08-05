from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects import EventCondition, Money


@dataclass
class EducationExpenseBand:
    """特定の子供が指定の期間にいる間、毎月発生する教育費（小学校・塾・中学・高校・大学等）。

    同じ子供に複数のBandが同時に該当してもよい（例: 小学校＋塾を並行して計上）。
    start_condition/end_conditionは収入・支出のstart_condition/end_conditionと同じ
    EventConditionで、"plan_start"（プラン開始時から）・"age"（学年基準、4月1日時点の年齢）・
    "date"（年月を直接指定）のいずれかを指定する。ageタイプは開始・終了ともにその年齢を含む
    （旧start_age/end_ageの「start_age <= 学年年齢 <= end_age」という仕様をそのまま維持する。
    終了年齢に達した学年もまだ発生する）。dateタイプは収入・支出の終了条件と同じ規約で、
    終了月自体は含まない（終了月から発生しなくなる）。
    monthly_amountは「プラン開始時点（今日）の価値」として入力する前提で、発生する年まで
    プラン共通のインフレ率で複利計算してから計上される
    （core/simulation/projection/projection_engine.py の_education_expense_monthly_total）。
    """

    band_id: str
    child_id: str
    category: str
    start_condition: EventCondition
    end_condition: EventCondition
    monthly_amount: Money


@dataclass
class OneTimeEducationExpense:
    """特定の子供に紐づく単発の教育費（入学金・受験費用等）。triggerで指定した年月に
    amount全額が一括で計上される（一般の単発支出（OneTimeExpense）の教育費版）。

    triggerが"age"タイプの場合、一般の単発支出・マイルストーンとは異なりプラン本人ではなく
    該当する子供（child_id、Childに登録された生年月日）の年齢を基準に解決する
    （EducationExpenseBandのage条件が子供基準であるのと同じ考え方。ただしEducationExpenseBandの
    ageは学年（4月1日）基準なのに対し、こちらは一般の単発支出と同じ誕生日基準の年齢。
    学年に正確に合わせたい場合はdateタイプで直接年月を指定する）。
    amountは「プラン開始時点（今日）の価値」として入力する前提で、発生年までプラン共通の
    インフレ率で複利計算してから計上される
    （core/simulation/projection/projection_engine.py の_one_time_education_expenses_by_month_offset）。
    """

    band_id: str
    child_id: str
    category: str
    amount: Money
    trigger: EventCondition
