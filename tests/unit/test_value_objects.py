import unittest
from datetime import date
from decimal import Decimal

from core.domain.value_objects import (
    AgeAt,
    EventCondition,
    EventConditionType,
    FiscalYear,
    Money,
    Rate,
)


class MoneyTest(unittest.TestCase):
    def test_add_and_subtract_round_to_whole_yen(self) -> None:
        a = Money.of(1000)
        b = Money.of(500.4)
        self.assertEqual((a + b).amount, Decimal("1500"))
        self.assertEqual((a - b).amount, Decimal("500"))

    def test_multiply_by_rate(self) -> None:
        principal = Money.of(1_000_000)
        rate = Rate.from_percent(5)
        self.assertEqual((principal * rate).amount, Decimal("50000"))

    def test_different_currency_raises(self) -> None:
        yen = Money.of(100, "JPY")
        usd = Money.of(100, "USD")
        with self.assertRaises(ValueError):
            yen + usd

    def test_is_negative(self) -> None:
        self.assertTrue(Money.of(-1).is_negative)
        self.assertFalse(Money.zero().is_negative)


class RateTest(unittest.TestCase):
    def test_from_percent(self) -> None:
        self.assertEqual(Rate.from_percent(5).value, Decimal("0.05"))

    def test_apply_to_money(self) -> None:
        rate = Rate.of("0.1")
        self.assertEqual(rate.apply_to(Money.of(10_000)).amount, Decimal("1000"))


class AgeAtTest(unittest.TestCase):
    def test_years_before_birthday(self) -> None:
        age = AgeAt(date(1990, 4, 1), date(2026, 3, 31))
        self.assertEqual(age.years, 35)

    def test_years_on_birthday(self) -> None:
        age = AgeAt(date(1990, 4, 1), date(2026, 4, 1))
        self.assertEqual(age.years, 36)

    def test_reference_before_birth_raises(self) -> None:
        with self.assertRaises(ValueError):
            AgeAt(date(2000, 1, 1), date(1999, 1, 1))


class FiscalYearTest(unittest.TestCase):
    def test_from_date_before_april_belongs_to_previous_fiscal_year(self) -> None:
        self.assertEqual(FiscalYear.from_date(date(2026, 3, 31)).year, 2025)

    def test_from_date_on_april_first(self) -> None:
        self.assertEqual(FiscalYear.from_date(date(2026, 4, 1)).year, 2026)

    def test_contains(self) -> None:
        fy = FiscalYear(2026)
        self.assertTrue(fy.contains(date(2027, 3, 31)))
        self.assertFalse(fy.contains(date(2027, 4, 1)))


class EventConditionTest(unittest.TestCase):
    def test_age_condition_requires_age(self) -> None:
        with self.assertRaises(ValueError):
            EventCondition(condition_type=EventConditionType.AGE)

    def test_at_age_factory(self) -> None:
        condition = EventCondition.at_age(60)
        self.assertEqual(condition.age, 60)


if __name__ == "__main__":
    unittest.main()
