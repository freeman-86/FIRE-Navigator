import unittest

from adapters.sheets.sheet_mapping import (
    EMPLOYEE_PENSION_ESTIMATE_HEADER,
    LIFE_EXPECTANCY_HEADER,
    NATIONAL_PENSION_ESTIMATE_HEADER,
    PENSION_CLAIM_AGE_HEADER,
    PENSION_CLAIM_TIMING_HEADER,
    PLAN_SHEET,
    RETIREMENT_AGE_HEADER,
    TARGET_ENDING_NETWORTH_HEADER,
)
from adapters.sheets.sheets_input_adapter import (
    _build_life_expectancy_age,
    _build_milestones,
    _build_pension,
    _parse_rate,
    read_target_ending_networth,
)
from core.domain.errors import StructuralInputError
from core.domain.milestone import MilestoneType
from core.domain.pension import ClaimTimingType
from core.domain.plan import DEFAULT_LIFE_EXPECTANCY_AGE
from core.domain.value_objects import EventConditionType, Money, Rate


class _FakeWorksheet:
    def __init__(self, values):
        self._values = values

    def get_all_values(self):
        return self._values


class _FakeSpreadsheet:
    def __init__(self, worksheet: _FakeWorksheet):
        self._worksheet = worksheet

    def worksheet(self, name):
        assert name == PLAN_SHEET
        return self._worksheet


class BuildPensionTest(unittest.TestCase):
    def test_all_blank_falls_back_to_backward_compatible_defaults(self) -> None:
        pension = _build_pension({})

        self.assertEqual(pension.national_pension.estimate_annual, Money.zero())
        self.assertEqual(pension.employee_pension.estimate_annual, Money.zero())
        self.assertEqual(pension.claim_timing.timing_type, ClaimTimingType.STANDARD)
        self.assertEqual(pension.claim_timing.age, 65)

    def test_fully_specified_values_are_used(self) -> None:
        settings = {
            NATIONAL_PENSION_ESTIMATE_HEADER: "780000",
            EMPLOYEE_PENSION_ESTIMATE_HEADER: "1200000",
            PENSION_CLAIM_TIMING_HEADER: "deferred",
            PENSION_CLAIM_AGE_HEADER: "70",
        }

        pension = _build_pension(settings)

        self.assertEqual(pension.national_pension.estimate_annual, Money.of(780_000))
        self.assertEqual(pension.employee_pension.estimate_annual, Money.of(1_200_000))
        self.assertEqual(pension.claim_timing.timing_type, ClaimTimingType.DEFERRED)
        self.assertEqual(pension.claim_timing.age, 70)

    def test_invalid_claim_timing_raises_structural_input_error(self) -> None:
        settings = {PENSION_CLAIM_TIMING_HEADER: "not_a_real_timing"}

        with self.assertRaises(StructuralInputError) as ctx:
            _build_pension(settings)
        self.assertEqual(ctx.exception.field_path, f"{PLAN_SHEET}!{PENSION_CLAIM_TIMING_HEADER}")


class BuildMilestonesTest(unittest.TestCase):
    def test_blank_retirement_age_yields_no_milestones(self) -> None:
        self.assertEqual(_build_milestones({}), [])

    def test_retirement_age_builds_retirement_milestone(self) -> None:
        milestones = _build_milestones({RETIREMENT_AGE_HEADER: "60"})

        self.assertEqual(len(milestones), 1)
        self.assertEqual(milestones[0].milestone_type, MilestoneType.RETIREMENT)
        self.assertEqual(milestones[0].trigger.condition_type, EventConditionType.AGE)
        self.assertEqual(milestones[0].trigger.age, 60)

    def test_non_numeric_retirement_age_raises_structural_input_error(self) -> None:
        with self.assertRaises(StructuralInputError) as ctx:
            _build_milestones({RETIREMENT_AGE_HEADER: "sixty"})
        self.assertEqual(ctx.exception.field_path, f"{PLAN_SHEET}!{RETIREMENT_AGE_HEADER}")


class BuildLifeExpectancyAgeTest(unittest.TestCase):
    def test_blank_defaults_to_default_life_expectancy_age(self) -> None:
        self.assertEqual(_build_life_expectancy_age({}), DEFAULT_LIFE_EXPECTANCY_AGE)

    def test_reads_specified_value(self) -> None:
        self.assertEqual(_build_life_expectancy_age({LIFE_EXPECTANCY_HEADER: "85"}), 85)

    def test_non_numeric_value_raises_structural_input_error(self) -> None:
        with self.assertRaises(StructuralInputError) as ctx:
            _build_life_expectancy_age({LIFE_EXPECTANCY_HEADER: "hundred"})
        self.assertEqual(ctx.exception.field_path, f"{PLAN_SHEET}!{LIFE_EXPECTANCY_HEADER}")


class ParseRateTest(unittest.TestCase):
    def test_plain_decimal_string_is_parsed_as_is(self) -> None:
        self.assertEqual(_parse_rate("0.07", "field"), Rate.of("0.07"))

    def test_percent_display_format_is_converted_back_to_a_decimal(self) -> None:
        # 比率列にパーセント表示形式(0.00%)を設定しているため、get_all_values()/get_all_records()
        # 経由で表示後の文字列("7.00%")がそのまま返ってくることがある。生の小数(0.07)として
        # 解釈できなければならない。
        self.assertEqual(_parse_rate("7.00%", "field"), Rate.of("0.07"))
        self.assertEqual(_parse_rate("100.00%", "field"), Rate.of("1"))
        self.assertEqual(_parse_rate("0.00%", "field"), Rate.zero())

    def test_non_numeric_value_raises_structural_input_error(self) -> None:
        with self.assertRaises(StructuralInputError) as ctx:
            _parse_rate("not_a_rate", "field")
        self.assertEqual(ctx.exception.field_path, "field")


class ReadTargetEndingNetworthTest(unittest.TestCase):
    def test_blank_defaults_to_zero(self) -> None:
        spreadsheet = _FakeSpreadsheet(_FakeWorksheet([["プランID", "plan_001"]]))
        self.assertEqual(read_target_ending_networth(spreadsheet), Money.zero())

    def test_reads_specified_value(self) -> None:
        spreadsheet = _FakeSpreadsheet(_FakeWorksheet([[TARGET_ENDING_NETWORTH_HEADER, "50000000"]]))
        self.assertEqual(read_target_ending_networth(spreadsheet), Money.of(50_000_000))


if __name__ == "__main__":
    unittest.main()
