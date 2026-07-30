import unittest

from adapters.local.local_data_adapter import (
    _build_assumptions,
    _build_life_expectancy_age,
    _build_pension,
    _build_user,
    _parse_rate,
    read_target_ending_networth,
)
from core.domain.errors import SchemaValidationError
from core.domain.plan import DEFAULT_LIFE_EXPECTANCY_AGE
from core.domain.value_objects import Money, Rate


class BuildUserTest(unittest.TestCase):
    def test_reads_birth_date(self) -> None:
        user = _build_user({"user": {"birth_date": "1990-04-01"}})
        self.assertEqual(user.birth_date.isoformat(), "1990-04-01")

    def test_missing_birth_date_raises_schema_validation_error(self) -> None:
        with self.assertRaises(SchemaValidationError) as ctx:
            _build_user({"user": {}})
        self.assertEqual(ctx.exception.field_path, "user.birth_date")

    def test_missing_user_section_raises_schema_validation_error(self) -> None:
        with self.assertRaises(SchemaValidationError):
            _build_user({})

    def test_no_spouse_section_means_no_spouse(self) -> None:
        user = _build_user({"user": {"birth_date": "1990-04-01"}})
        self.assertIsNone(user.spouse)

    def test_spouse_with_blank_birth_date_means_no_spouse(self) -> None:
        user = _build_user({"user": {"birth_date": "1990-04-01", "spouse": {"birth_date": None}}})
        self.assertIsNone(user.spouse)

    def test_spouse_with_birth_date_is_read(self) -> None:
        user = _build_user(
            {"user": {"birth_date": "1990-04-01", "spouse": {"birth_date": "1992-06-01"}}}
        )
        self.assertIsNotNone(user.spouse)
        self.assertEqual(user.spouse.birth_date.isoformat(), "1992-06-01")

    def test_spouse_with_invalid_birth_date_raises_schema_validation_error(self) -> None:
        with self.assertRaises(SchemaValidationError) as ctx:
            _build_user({"user": {"birth_date": "1990-04-01", "spouse": {"birth_date": "not-a-date"}}})
        self.assertEqual(ctx.exception.field_path, "user.spouse.birth_date")


class BuildAssumptionsTest(unittest.TestCase):
    def test_reads_inflation_rate(self) -> None:
        assumptions = _build_assumptions({"assumptions": {"inflation_rate": "0.02"}})
        self.assertEqual(assumptions.inflation_rate, Rate.of("0.02"))

    def test_missing_inflation_rate_raises_schema_validation_error(self) -> None:
        with self.assertRaises(SchemaValidationError) as ctx:
            _build_assumptions({"assumptions": {}})
        self.assertEqual(ctx.exception.field_path, "assumptions.inflation_rate")


class BuildPensionTest(unittest.TestCase):
    def test_all_blank_falls_back_to_backward_compatible_defaults(self) -> None:
        pension = _build_pension({})

        self.assertEqual(pension.national_pension.estimate_annual, Money.zero())
        self.assertEqual(pension.employee_pension.estimate_annual, Money.zero())
        self.assertEqual(pension.claim_timing.age, 65)

    def test_fully_specified_values_are_used(self) -> None:
        data = {
            "pension": {
                "national_pension_estimate_annual": 780000,
                "employee_pension_estimate_annual": 1200000,
                "claim_age": 70,
            }
        }

        pension = _build_pension(data)

        self.assertEqual(pension.national_pension.estimate_annual, Money.of(780_000))
        self.assertEqual(pension.employee_pension.estimate_annual, Money.of(1_200_000))
        self.assertEqual(pension.claim_timing.age, 70)


class BuildLifeExpectancyAgeTest(unittest.TestCase):
    def test_blank_defaults_to_default_life_expectancy_age(self) -> None:
        self.assertEqual(_build_life_expectancy_age({}), DEFAULT_LIFE_EXPECTANCY_AGE)

    def test_reads_specified_value(self) -> None:
        self.assertEqual(_build_life_expectancy_age({"life_expectancy_age": 85}), 85)

    def test_non_numeric_value_raises_schema_validation_error(self) -> None:
        with self.assertRaises(SchemaValidationError) as ctx:
            _build_life_expectancy_age({"life_expectancy_age": "hundred"})
        self.assertEqual(ctx.exception.field_path, "life_expectancy_age")


class ParseRateTest(unittest.TestCase):
    def test_plain_decimal_string_is_parsed_as_is(self) -> None:
        self.assertEqual(_parse_rate("0.07", "field"), Rate.of("0.07"))

    def test_number_is_parsed_as_is(self) -> None:
        self.assertEqual(_parse_rate(0.05, "field"), Rate.of("0.05"))

    def test_non_numeric_value_raises_schema_validation_error(self) -> None:
        with self.assertRaises(SchemaValidationError) as ctx:
            _parse_rate("not_a_rate", "field")
        self.assertEqual(ctx.exception.field_path, "field")


class ReadTargetEndingNetworthTest(unittest.TestCase):
    def test_blank_defaults_to_zero(self) -> None:
        self.assertEqual(read_target_ending_networth({}), Money.zero())

    def test_reads_specified_value(self) -> None:
        self.assertEqual(read_target_ending_networth({"target_ending_networth": 50000000}), Money.of(50_000_000))


if __name__ == "__main__":
    unittest.main()
