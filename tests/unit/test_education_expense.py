import unittest

from core.domain.education_expense import EducationExpenseBand
from core.domain.value_objects import Money


class EducationExpenseBandTest(unittest.TestCase):
    def test_applies_to_age_within_inclusive_range(self) -> None:
        band = EducationExpenseBand(
            band_id="band_elementary",
            child_id="child_001",
            category="小学校",
            start_age=6,
            end_age=11,
            monthly_amount=Money.of(20_000),
        )

        self.assertFalse(band.applies_to_age(5))
        self.assertTrue(band.applies_to_age(6))
        self.assertTrue(band.applies_to_age(11))
        self.assertFalse(band.applies_to_age(12))

    def test_end_age_before_start_age_raises(self) -> None:
        with self.assertRaises(ValueError):
            EducationExpenseBand(
                band_id="band_invalid",
                child_id="child_001",
                category="不正",
                start_age=10,
                end_age=5,
                monthly_amount=Money.zero(),
            )


if __name__ == "__main__":
    unittest.main()
