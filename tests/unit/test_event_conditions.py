import unittest
from datetime import date

from core.domain.value_objects import EventCondition
from core.simulation.projection.event_conditions import resolve_condition_month

BIRTH_DATE = date(1990, 4, 15)


class ResolveConditionMonthTest(unittest.TestCase):
    def test_today_and_plan_start_resolve_to_start_year_month(self) -> None:
        self.assertEqual(resolve_condition_month(EventCondition.today(), 2026, 7, BIRTH_DATE), (2026, 7))
        self.assertEqual(resolve_condition_month(EventCondition.plan_start(), 2026, 7, BIRTH_DATE), (2026, 7))

    def test_date_condition_resolves_to_its_own_year_and_month(self) -> None:
        condition = EventCondition.at_date(date(2030, 11, 3))
        self.assertEqual(resolve_condition_month(condition, 2026, 1, BIRTH_DATE), (2030, 11))

    def test_age_condition_resolves_to_birthday_month_in_the_target_year(self) -> None:
        condition = EventCondition.at_age(45)
        # 1990-04-15生まれが45歳になるのは2035年4月
        self.assertEqual(resolve_condition_month(condition, 2026, 1, BIRTH_DATE), (2035, 4))

    def test_networth_multiple_condition_is_not_statically_resolvable(self) -> None:
        condition = EventCondition.networth_multiple_of_expense(25)
        self.assertIsNone(resolve_condition_month(condition, 2026, 1, BIRTH_DATE))


if __name__ == "__main__":
    unittest.main()
