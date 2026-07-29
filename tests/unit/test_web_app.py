import json
import tempfile
import unittest
from pathlib import Path

from web.app import EMPTY_PLAN, app

_MINIMAL_VALID_DATA = {
    "schema_version": 1,
    "plan_id": "plan_001",
    "name": "テストプラン",
    "user": {"birth_date": "1990-04-01"},
    "assumptions": {"inflation_rate": "0.02"},
    "target_ending_networth": 5000000,
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


class WebAppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        app.config["TESTING"] = True
        # テストが本物のdata/plan.jsonへ絶対触れないよう、毎回テンポラリファイルへ差し替える。
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._original_plan_file_path = app.config["PLAN_FILE_PATH"]
        app.config["PLAN_FILE_PATH"] = Path(self._tmp_dir.name) / "plan.json"
        self.client = app.test_client()

    def tearDown(self) -> None:
        app.config["PLAN_FILE_PATH"] = self._original_plan_file_path
        self._tmp_dir.cleanup()


class IndexRouteTest(WebAppTestCase):
    def test_serves_html_page(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"FIRE Navigator", response.data)


class ApiPlanRouteTest(WebAppTestCase):
    def test_get_returns_empty_plan_when_file_does_not_exist(self) -> None:
        response = self.client.get("/api/plan")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), EMPTY_PLAN)

    def test_post_saves_valid_data_and_get_returns_it_back(self) -> None:
        post_response = self.client.post("/api/plan", json=_MINIMAL_VALID_DATA)
        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(post_response.get_json(), {"saved": True})

        get_response = self.client.get("/api/plan")
        self.assertEqual(get_response.get_json()["plan_id"], "plan_001")

    def test_post_invalid_data_returns_422_and_does_not_create_file(self) -> None:
        invalid_data = {**_MINIMAL_VALID_DATA, "user": {}}

        response = self.client.post("/api/plan", json=invalid_data)

        self.assertEqual(response.status_code, 422)
        self.assertIn("errors", response.get_json())
        self.assertFalse(Path(app.config["PLAN_FILE_PATH"]).exists())


class ApiRunRouteTest(WebAppTestCase):
    def test_valid_plan_returns_dashboard_and_charts(self) -> None:
        response = self.client.post("/api/run", json=_MINIMAL_VALID_DATA)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["errors"], [])
        self.assertEqual(body["plan_id"], "plan_001")
        self.assertIsNotNone(body["dashboard"])
        self.assertIsNotNone(body["charts"]["networth_chart"])
        self.assertIsNone(body["charts"]["montecarlo_distribution_chart"])

    def test_valid_plan_is_saved_to_disk(self) -> None:
        self.client.post("/api/run", json=_MINIMAL_VALID_DATA)

        saved = json.loads(Path(app.config["PLAN_FILE_PATH"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["plan_id"], "plan_001")

    def test_invalid_data_returns_422_and_does_not_run_or_save(self) -> None:
        invalid_data = {**_MINIMAL_VALID_DATA, "accounts": [{"account_id": "acc_1"}]}  # account_type欠落

        response = self.client.post("/api/run", json=invalid_data)

        self.assertEqual(response.status_code, 422)
        self.assertIn("errors", response.get_json())
        self.assertFalse(Path(app.config["PLAN_FILE_PATH"]).exists())


class ApiRegistryRoutesTest(WebAppTestCase):
    def test_asset_classes_returns_registry(self) -> None:
        response = self.client.get("/api/asset-classes")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cash", response.get_json())

    def test_account_types_returns_all_enum_values(self) -> None:
        response = self.client.get("/api/account-types")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cash", response.get_json())
        self.assertIn("nisa_growth", response.get_json())


if __name__ == "__main__":
    unittest.main()
