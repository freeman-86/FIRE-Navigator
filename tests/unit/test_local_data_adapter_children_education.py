import unittest

from adapters.local.local_data_adapter import _build_children_and_education_expenses
from core.domain.errors import SchemaValidationError
from core.domain.value_objects import EventConditionType, Money


class BuildChildrenAndEducationExpensesTest(unittest.TestCase):
    def test_missing_sections_return_empty_lists(self) -> None:
        children, bands, one_time_bands = _build_children_and_education_expenses({})
        self.assertEqual(children, [])
        self.assertEqual(bands, [])
        self.assertEqual(one_time_bands, [])

    def test_builds_children_and_recurring_bands_with_age_conditions(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {
                    "band_id": "band_elementary",
                    "child_id": "child_001",
                    "category": "小学校",
                    "kind": "recurring",
                    "start_condition": {"type": "age", "age": 6},
                    "end_condition": {"type": "age", "age": 11},
                    "monthly_amount": 20000,
                }
            ],
        }

        children, bands, one_time_bands = _build_children_and_education_expenses(data)

        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].child_id, "child_001")
        self.assertEqual(children[0].birth_date.isoformat(), "2022-04-01")
        self.assertEqual(len(bands), 1)
        self.assertEqual(one_time_bands, [])
        self.assertEqual(bands[0].monthly_amount, Money.of(20_000))
        self.assertEqual(bands[0].start_condition.condition_type, EventConditionType.AGE)
        self.assertEqual(bands[0].start_condition.age, 6)
        self.assertEqual(bands[0].end_condition.age, 11)

    def test_builds_recurring_bands_with_date_conditions(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2015-04-01"}],
            "education_expenses": [
                {
                    "band_id": "band_juku",
                    "child_id": "child_001",
                    "category": "塾",
                    "kind": "recurring",
                    "start_condition": {"type": "date", "date": "2026-06-01"},
                    "end_condition": {"type": "date", "date": "2026-09-01"},
                    "monthly_amount": 15000,
                }
            ],
        }

        _, bands, _ = _build_children_and_education_expenses(data)

        self.assertEqual(bands[0].start_condition.condition_type, EventConditionType.DATE)
        self.assertEqual(bands[0].start_condition.date.isoformat(), "2026-06-01")
        self.assertEqual(bands[0].end_condition.date.isoformat(), "2026-09-01")

    def test_builds_one_time_band_with_age_trigger(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2015-04-01"}],
            "education_expenses": [
                {
                    "band_id": "band_entrance_fee",
                    "child_id": "child_001",
                    "category": "入学金",
                    "kind": "one_time",
                    "trigger": {"type": "age", "age": 12},
                    "amount": 300000,
                }
            ],
        }

        _, bands, one_time_bands = _build_children_and_education_expenses(data)

        self.assertEqual(bands, [])
        self.assertEqual(len(one_time_bands), 1)
        self.assertEqual(one_time_bands[0].band_id, "band_entrance_fee")
        self.assertEqual(one_time_bands[0].child_id, "child_001")
        self.assertEqual(one_time_bands[0].amount, Money.of(300_000))
        self.assertEqual(one_time_bands[0].trigger.condition_type, EventConditionType.AGE)
        self.assertEqual(one_time_bands[0].trigger.age, 12)

    def test_builds_one_time_band_with_date_trigger(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2015-04-01"}],
            "education_expenses": [
                {
                    "band_id": "band_exam_fee",
                    "child_id": "child_001",
                    "category": "受験費用",
                    "kind": "one_time",
                    "trigger": {"type": "date", "date": "2033-01-01"},
                    "amount": 100000,
                }
            ],
        }

        _, _, one_time_bands = _build_children_and_education_expenses(data)

        self.assertEqual(one_time_bands[0].trigger.condition_type, EventConditionType.DATE)
        self.assertEqual(one_time_bands[0].trigger.date.isoformat(), "2033-01-01")

    def test_one_time_blank_amount_defaults_to_zero(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {
                    "band_id": "b1",
                    "child_id": "child_001",
                    "category": "x",
                    "kind": "one_time",
                    "trigger": {"type": "age", "age": 12},
                }
            ],
        }

        _, _, one_time_bands = _build_children_and_education_expenses(data)

        self.assertEqual(one_time_bands[0].amount, Money.zero())

    def test_one_time_missing_trigger_raises_schema_validation_error(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {"band_id": "b1", "child_id": "child_001", "category": "x", "kind": "one_time", "amount": 100000}
            ],
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_children_and_education_expenses(data)
        self.assertEqual(ctx.exception.field_path, "education_expenses[0].trigger")

    def test_one_time_row_with_start_condition_raises_schema_validation_error(self) -> None:
        # kind=one_timeの行にrecurring専用の項目が入っていたら拒否する（支出と同じ設計）。
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {
                    "band_id": "b1",
                    "child_id": "child_001",
                    "category": "x",
                    "kind": "one_time",
                    "trigger": {"type": "age", "age": 12},
                    "amount": 100000,
                    "start_condition": {"type": "age", "age": 6},
                }
            ],
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_children_and_education_expenses(data)
        self.assertEqual(ctx.exception.field_path, "education_expenses[0]")

    def test_blank_monthly_amount_defaults_to_zero(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {
                    "band_id": "b1",
                    "child_id": "child_001",
                    "category": "x",
                    "kind": "recurring",
                    "start_condition": {"type": "age", "age": 6},
                    "end_condition": {"type": "age", "age": 11},
                }
            ],
        }

        _, bands, _ = _build_children_and_education_expenses(data)

        self.assertEqual(bands[0].monthly_amount, Money.zero())

    def test_band_referencing_unknown_child_id_raises_schema_validation_error(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {
                    "band_id": "b1",
                    "child_id": "child_002",
                    "category": "x",
                    "kind": "recurring",
                    "start_condition": {"type": "age", "age": 6},
                    "end_condition": {"type": "age", "age": 11},
                }
            ],
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_children_and_education_expenses(data)
        self.assertEqual(ctx.exception.field_path, "education_expenses[0].child_id")

    def test_unknown_kind_raises_schema_validation_error(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [{"band_id": "b1", "child_id": "child_001", "category": "x", "kind": "monthly"}],
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_children_and_education_expenses(data)
        self.assertEqual(ctx.exception.field_path, "education_expenses[0].kind")

    def test_missing_start_condition_raises_schema_validation_error(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {
                    "band_id": "b1",
                    "child_id": "child_001",
                    "category": "x",
                    "kind": "recurring",
                    "end_condition": {"type": "age", "age": 11},
                }
            ],
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_children_and_education_expenses(data)
        self.assertEqual(ctx.exception.field_path, "education_expenses[0].start_condition")

    def test_missing_end_condition_raises_schema_validation_error(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {
                    "band_id": "b1",
                    "child_id": "child_001",
                    "category": "x",
                    "kind": "recurring",
                    "start_condition": {"type": "age", "age": 6},
                }
            ],
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_children_and_education_expenses(data)
        self.assertEqual(ctx.exception.field_path, "education_expenses[0].end_condition")


if __name__ == "__main__":
    unittest.main()
