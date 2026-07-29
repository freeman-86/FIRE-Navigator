import unittest

from adapters.local.local_data_adapter import _build_expenses, _build_incomes
from core.domain.errors import SchemaValidationError
from core.domain.value_objects import EventCondition, Money, Rate

_DEFAULT_GROWTH_RATE = Rate.of("0.02")


class BuildIncomesTest(unittest.TestCase):
    def test_reads_all_fields(self) -> None:
        data = {
            "incomes": [
                {
                    "income_id": "income_1",
                    "source": "salary",
                    "amount": 6000000,
                    "growth_rate": "0.01",
                    "start_condition": {"type": "plan_start"},
                    "end_condition": {"type": "age", "age": 60},
                }
            ]
        }

        incomes = _build_incomes(data, _DEFAULT_GROWTH_RATE)

        self.assertEqual(len(incomes), 1)
        income = incomes[0]
        self.assertEqual(income.income_id, "income_1")
        self.assertEqual(income.source, "salary")
        self.assertEqual(income.amount, Money.of(6_000_000))
        self.assertEqual(income.growth_rate, Rate.of("0.01"))
        self.assertEqual(income.start_condition, EventCondition.plan_start())
        self.assertEqual(income.end_condition, EventCondition.at_age(60))

    def test_blank_growth_rate_defaults_to_inflation_rate(self) -> None:
        data = {
            "incomes": [
                {
                    "income_id": "income_1",
                    "source": "salary",
                    "amount": 6000000,
                    "growth_rate": None,
                    "start_condition": {"type": "plan_start"},
                }
            ]
        }

        incomes = _build_incomes(data, _DEFAULT_GROWTH_RATE)

        self.assertEqual(incomes[0].growth_rate, _DEFAULT_GROWTH_RATE)

    def test_end_condition_is_optional(self) -> None:
        data = {
            "incomes": [
                {"income_id": "income_1", "source": "salary", "amount": 6000000, "start_condition": {"type": "plan_start"}}
            ]
        }

        incomes = _build_incomes(data, _DEFAULT_GROWTH_RATE)

        self.assertIsNone(incomes[0].end_condition)

    def test_missing_start_condition_raises_schema_validation_error(self) -> None:
        data = {"incomes": [{"income_id": "income_1", "source": "salary", "amount": 6000000}]}

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_incomes(data, _DEFAULT_GROWTH_RATE)
        self.assertEqual(ctx.exception.field_path, "incomes[0].start_condition")

    def test_unknown_condition_type_raises_schema_validation_error(self) -> None:
        data = {
            "incomes": [
                {
                    "income_id": "income_1",
                    "source": "salary",
                    "amount": 6000000,
                    "start_condition": {"type": "retirement"},
                }
            ]
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_incomes(data, _DEFAULT_GROWTH_RATE)
        self.assertEqual(ctx.exception.field_path, "incomes[0].start_condition")


class BuildExpensesTest(unittest.TestCase):
    def test_recurring_expense_reads_all_fields(self) -> None:
        data = {
            "expenses": [
                {
                    "expense_id": "expense_living",
                    "category": "living",
                    "kind": "recurring",
                    "amount": 3600000,
                    "growth_rate": "0.02",
                    "start_condition": None,
                    "end_condition": None,
                }
            ]
        }

        expenses, one_time_expenses = _build_expenses(data, _DEFAULT_GROWTH_RATE)

        self.assertEqual(len(expenses), 1)
        self.assertEqual(one_time_expenses, [])
        expense = expenses[0]
        self.assertEqual(expense.expense_id, "expense_living")
        self.assertEqual(expense.amount, Money.of(3_600_000))
        self.assertEqual(expense.growth_rate, Rate.of("0.02"))
        self.assertIsNone(expense.start_condition)
        self.assertIsNone(expense.end_condition)

    def test_recurring_expense_blank_growth_rate_defaults_to_inflation_rate(self) -> None:
        data = {
            "expenses": [
                {"expense_id": "expense_living", "category": "living", "kind": "recurring", "amount": 3600000}
            ]
        }

        expenses, _ = _build_expenses(data, _DEFAULT_GROWTH_RATE)

        self.assertEqual(expenses[0].growth_rate, _DEFAULT_GROWTH_RATE)

    def test_recurring_expense_start_and_end_condition_are_optional(self) -> None:
        # Income と異なり経常支出は開始条件も任意（両方省略した行はプラン全期間で発生する）
        data = {"expenses": [{"expense_id": "expense_living", "category": "living", "kind": "recurring", "amount": 100}]}

        expenses, _ = _build_expenses(data, _DEFAULT_GROWTH_RATE)

        self.assertIsNone(expenses[0].start_condition)
        self.assertIsNone(expenses[0].end_condition)

    def test_one_time_expense_reads_amount_and_trigger(self) -> None:
        data = {
            "expenses": [
                {
                    "expense_id": "expense_car",
                    "category": "車の買い替え",
                    "kind": "one_time",
                    "amount": 3000000,
                    "trigger": {"type": "age", "age": 45},
                }
            ]
        }

        expenses, one_time_expenses = _build_expenses(data, _DEFAULT_GROWTH_RATE)

        self.assertEqual(expenses, [])
        self.assertEqual(len(one_time_expenses), 1)
        one_time_expense = one_time_expenses[0]
        self.assertEqual(one_time_expense.amount, Money.of(3_000_000))
        self.assertEqual(one_time_expense.trigger, EventCondition.at_age(45))

    def test_one_time_expense_missing_trigger_raises_schema_validation_error(self) -> None:
        data = {"expenses": [{"expense_id": "expense_car", "category": "車", "kind": "one_time", "amount": 3000000}]}

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_expenses(data, _DEFAULT_GROWTH_RATE)
        self.assertEqual(ctx.exception.field_path, "expenses[0].trigger")

    def test_one_time_expense_with_growth_rate_field_is_rejected(self) -> None:
        # kind=one_timeの行にはgrowth_rate等、経常支出専用の項目は許可しない
        # （Sheets版のように黙って無視するのではなく、フォームが作らないはずの形として早期に拒否する）
        data = {
            "expenses": [
                {
                    "expense_id": "expense_car",
                    "category": "車",
                    "kind": "one_time",
                    "amount": 3000000,
                    "trigger": {"type": "age", "age": 45},
                    "growth_rate": "0.02",
                }
            ]
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_expenses(data, _DEFAULT_GROWTH_RATE)
        self.assertIn("growth_rate", ctx.exception.message)

    def test_recurring_expense_with_trigger_field_is_rejected(self) -> None:
        data = {
            "expenses": [
                {
                    "expense_id": "expense_living",
                    "category": "living",
                    "kind": "recurring",
                    "amount": 100,
                    "trigger": {"type": "age", "age": 45},
                }
            ]
        }

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_expenses(data, _DEFAULT_GROWTH_RATE)
        self.assertIn("trigger", ctx.exception.message)

    def test_unknown_kind_raises_schema_validation_error(self) -> None:
        data = {"expenses": [{"expense_id": "expense_1", "category": "x", "kind": "quarterly", "amount": 100}]}

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_expenses(data, _DEFAULT_GROWTH_RATE)
        self.assertEqual(ctx.exception.field_path, "expenses[0].kind")

    def test_missing_kind_raises_schema_validation_error(self) -> None:
        data = {"expenses": [{"expense_id": "expense_1", "category": "x", "amount": 100}]}

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_expenses(data, _DEFAULT_GROWTH_RATE)
        self.assertEqual(ctx.exception.field_path, "expenses[0].kind")


if __name__ == "__main__":
    unittest.main()
