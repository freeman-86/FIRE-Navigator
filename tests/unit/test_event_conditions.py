import unittest
from datetime import date

from core.domain.value_objects import EventCondition
from core.simulation.projection.event_conditions import resolve_condition_month

BIRTH_DATE = date(1990, 4, 15)


class ResolveConditionMonthTest(unittest.TestCase):
    def test_plan_start_resolves_to_start_year_month(self) -> None:
        self.assertEqual(resolve_condition_month(EventCondition.plan_start(), 2026, 7, BIRTH_DATE), (2026, 7))

    def test_date_condition_resolves_to_its_own_year_and_month(self) -> None:
        condition = EventCondition.at_date(date(2030, 11, 3))
        self.assertEqual(resolve_condition_month(condition, 2026, 1, BIRTH_DATE), (2030, 11))

    def test_age_condition_resolves_to_the_month_age_at_first_shows_the_target_age(self) -> None:
        condition = EventCondition.at_age(45)
        # 1990-04-15生まれは2035-04-15に45歳になるが、age_at()は「その月の1日時点」で年齢を判定する
        # ため、誕生日が2日以降の場合は誕生月の1日はまだ誕生日前(44歳のまま)で、45歳と表示される
        # のは翌月(2035年5月)から。resolve_condition_month()はage_at()と同じ基準に揃える。
        self.assertEqual(resolve_condition_month(condition, 2026, 1, BIRTH_DATE), (2035, 5))

    def test_age_condition_resolves_to_birthday_month_when_born_on_the_first(self) -> None:
        condition = EventCondition.at_age(45)
        birth_date_on_first = date(1990, 4, 1)
        # 誕生日が月初(1日)の場合は、その月の1日時点で誕生日を迎えているため誕生月そのものになる。
        self.assertEqual(resolve_condition_month(condition, 2026, 1, birth_date_on_first), (2035, 4))

    def test_age_condition_rolls_over_to_january_when_born_in_december(self) -> None:
        condition = EventCondition.at_age(45)
        birth_date_in_december = date(1986, 12, 26)
        # 12月生まれ(1日生まれ以外)は、翌月が年をまたいで1月になる。
        self.assertEqual(resolve_condition_month(condition, 2026, 1, birth_date_in_december), (2032, 1))

    def test_networth_multiple_condition_is_not_statically_resolvable(self) -> None:
        condition = EventCondition.networth_multiple_of_expense(25)
        self.assertIsNone(resolve_condition_month(condition, 2026, 1, BIRTH_DATE))


if __name__ == "__main__":
    unittest.main()
