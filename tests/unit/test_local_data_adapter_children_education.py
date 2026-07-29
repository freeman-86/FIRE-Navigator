import unittest

from adapters.local.local_data_adapter import _build_children_and_education_expenses
from core.domain.errors import SchemaValidationError
from core.domain.value_objects import Money


class BuildChildrenAndEducationExpensesTest(unittest.TestCase):
    def test_missing_sections_return_empty_lists(self) -> None:
        children, bands = _build_children_and_education_expenses({})
        self.assertEqual(children, [])
        self.assertEqual(bands, [])

    def test_builds_children_and_bands(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {
                    "band_id": "band_elementary",
                    "child_id": "child_001",
                    "category": "小学校",
                    "start_age": 6,
                    "end_age": 11,
                    "monthly_amount": 20000,
                }
            ],
        }

        children, bands = _build_children_and_education_expenses(data)

        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].child_id, "child_001")
        self.assertEqual(children[0].birth_date.isoformat(), "2022-04-01")
        self.assertEqual(len(bands), 1)
        self.assertEqual(bands[0].monthly_amount, Money.of(20_000))

    def test_blank_monthly_amount_defaults_to_zero(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {"band_id": "b1", "child_id": "child_001", "category": "x", "start_age": 6, "end_age": 11}
            ],
        }

        _, bands = _build_children_and_education_expenses(data)

        self.assertEqual(bands[0].monthly_amount, Money.zero())

    def test_band_referencing_unknown_child_id_raises_schema_validation_error(self) -> None:
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {"band_id": "b1", "child_id": "child_002", "category": "x", "start_age": 6, "end_age": 11}
            ],
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_children_and_education_expenses(data)
        self.assertEqual(ctx.exception.field_path, "education_expenses[0].child_id")

    def test_end_age_before_start_age_raises_value_error_from_domain_layer(self) -> None:
        # EducationExpenseBand.__post_init__（core/domain層）のチェックがそのまま伝播することを確認する
        data = {
            "children": [{"child_id": "child_001", "birth_date": "2022-04-01"}],
            "education_expenses": [
                {"band_id": "b1", "child_id": "child_001", "category": "x", "start_age": 11, "end_age": 6}
            ],
        }

        with self.assertRaises(ValueError):
            _build_children_and_education_expenses(data)


if __name__ == "__main__":
    unittest.main()
