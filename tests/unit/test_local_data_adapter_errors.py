import unittest

from adapters.local.local_data_adapter import build_plan_from_local_file
from core.domain.errors import SchemaValidationError
from core.domain.plan import StartConditionType

_MINIMAL_VALID_DATA = {
    "plan_id": "plan_001",
    "name": "テストプラン",
    "user": {"birth_date": "1990-04-01"},
    "assumptions": {"inflation_rate": "0.02"},
    "accounts": [],
    "incomes": [],
    "expenses": [],
}


class BuildPlanFromLocalFileTest(unittest.TestCase):
    def test_builds_a_minimal_plan(self) -> None:
        plan = build_plan_from_local_file(_MINIMAL_VALID_DATA)

        self.assertEqual(plan.plan_id, "plan_001")
        self.assertEqual(plan.name, "テストプラン")
        # 現状のSheetsアダプタと同じく、start_conditionは常にTODAY固定
        self.assertEqual(plan.start_condition.condition_type, StartConditionType.TODAY)
        # Sheetsアダプタから一度も設定されたことのないフィールドは既定値のまま
        self.assertEqual(plan.milestones, [])
        self.assertEqual(plan.debts, [])
        self.assertEqual(plan.loans, [])
        self.assertIsNone(plan.user.spouse)

    def test_missing_plan_id_raises_schema_validation_error(self) -> None:
        data = {**_MINIMAL_VALID_DATA}
        del data["plan_id"]

        with self.assertRaises(SchemaValidationError) as ctx:
            build_plan_from_local_file(data)
        self.assertEqual(ctx.exception.field_path, "plan_id")

    def test_missing_name_raises_schema_validation_error(self) -> None:
        data = {**_MINIMAL_VALID_DATA}
        del data["name"]

        with self.assertRaises(SchemaValidationError) as ctx:
            build_plan_from_local_file(data)
        self.assertEqual(ctx.exception.field_path, "name")

    def test_uses_default_withdrawal_and_contribution_strategy(self) -> None:
        # SheetsアダプタとPlan設定シートに項目がない以上、ローカル版も同じハードコードの
        # 既定値を使う（ユーザーが編集できる項目ではない、という現状の仕様を踏襲する）。
        plan = build_plan_from_local_file(_MINIMAL_VALID_DATA)

        self.assertTrue(len(plan.withdrawal_strategy.order) > 0)
        self.assertTrue(len(plan.contribution_strategy.order) > 0)


if __name__ == "__main__":
    unittest.main()
