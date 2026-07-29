import json
import tempfile
import unittest
from pathlib import Path

from adapters.local.local_data_adapter import load_plan, load_portfolios, save_plan
from core.domain.errors import SchemaValidationError

_MINIMAL_VALID_DATA = {
    "schema_version": 1,
    "plan_id": "plan_001",
    "name": "テストプラン",
    "user": {"birth_date": "1990-04-01"},
    "assumptions": {"inflation_rate": "0.02"},
    "accounts": [
        {
            "account_id": "acc_1",
            "account_type": "cash",
            "asset_class": "cash",
            "expected_return": "0.0",
            "current_value": 1000000,
        }
    ],
    "incomes": [],
    "expenses": [],
}


class SavePlanTest(unittest.TestCase):
    def test_saves_and_round_trips_through_load_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "plan.json"

            save_plan(_MINIMAL_VALID_DATA, path)
            plan = load_plan(path)

            self.assertEqual(plan.plan_id, "plan_001")
            self.assertEqual(plan.name, "テストプラン")

        # 保存されたファイルの中身自体もJSONとして妥当であることを確認する
        # （↑のwith文の外なのでファイルは既に消えているため、ブロック内でのplan検証で代替済み）

    def test_saved_file_round_trips_portfolios_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "plan.json"

            save_plan(_MINIMAL_VALID_DATA, path)
            portfolios = load_portfolios(path)

            self.assertEqual(set(portfolios.keys()), {"acc_1"})

    def test_invalid_data_raises_before_writing_and_leaves_no_file(self) -> None:
        invalid_data = {**_MINIMAL_VALID_DATA, "user": {}}  # birth_date欠落

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "plan.json"

            with self.assertRaises(SchemaValidationError):
                save_plan(invalid_data, path)

            self.assertFalse(path.exists())

    def test_invalid_data_does_not_overwrite_existing_valid_file(self) -> None:
        # 検証は書き込み前に行われるため、既存の正常なファイルが壊れた入力で破壊されないことを確認する
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "plan.json"
            save_plan(_MINIMAL_VALID_DATA, path)

            invalid_data = {**_MINIMAL_VALID_DATA, "assumptions": {}}
            with self.assertRaises(SchemaValidationError):
                save_plan(invalid_data, path)

            reloaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(reloaded["plan_id"], "plan_001")

    def test_creates_parent_directory_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "nested" / "dir" / "plan.json"

            save_plan(_MINIMAL_VALID_DATA, path)

            self.assertTrue(path.exists())

    def test_no_leftover_tmp_file_after_successful_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "plan.json"

            save_plan(_MINIMAL_VALID_DATA, path)

            self.assertEqual(list(Path(tmp_dir).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
