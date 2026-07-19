import unittest

import gspread

from adapters.sheets.sheet_mapping import AGE_HEADER, ALLOCATION_POLICY_SHEET, ASSET_CLASS_HEADER, TARGET_WEIGHT_HEADER
from adapters.sheets.sheets_input_adapter import _build_allocation_policy
from core.domain.errors import StructuralInputError
from core.domain.value_objects import Rate

ASSET_CLASS_REGISTRY = {"equity_sp500": "株式（S&P500連動）", "bond_us_treasury": "債券（米国長期国債）"}


class _FakeWorksheet:
    def __init__(self, records):
        self._records = records

    def get_all_records(self):
        return self._records


class _FakeSpreadsheet:
    def __init__(self, worksheets: dict):
        self._worksheets = worksheets

    def worksheet(self, name):
        if name not in self._worksheets:
            raise gspread.exceptions.WorksheetNotFound(name)
        return self._worksheets[name]


class BuildAllocationPolicyTest(unittest.TestCase):
    def test_missing_sheet_returns_none(self) -> None:
        spreadsheet = _FakeSpreadsheet({})
        self.assertIsNone(_build_allocation_policy(spreadsheet, ASSET_CLASS_REGISTRY))

    def test_groups_rows_by_age_into_targets(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                ALLOCATION_POLICY_SHEET: _FakeWorksheet(
                    records=[
                        {AGE_HEADER: "20", ASSET_CLASS_HEADER: "equity_sp500", TARGET_WEIGHT_HEADER: "0.8"},
                        {AGE_HEADER: "20", ASSET_CLASS_HEADER: "bond_us_treasury", TARGET_WEIGHT_HEADER: "0.2"},
                        {AGE_HEADER: "60", ASSET_CLASS_HEADER: "equity_sp500", TARGET_WEIGHT_HEADER: "0.4"},
                        {AGE_HEADER: "60", ASSET_CLASS_HEADER: "bond_us_treasury", TARGET_WEIGHT_HEADER: "0.6"},
                    ]
                )
            }
        )

        policy = _build_allocation_policy(spreadsheet, ASSET_CLASS_REGISTRY)

        self.assertEqual(len(policy.targets), 2)
        self.assertEqual(policy.targets[0].age, 20)
        self.assertEqual(policy.targets[0].weights["equity_sp500"], Rate.of("0.8"))
        self.assertEqual(policy.targets[1].age, 60)
        self.assertEqual(policy.targets[1].weights["bond_us_treasury"], Rate.of("0.6"))

    def test_unknown_asset_class_raises_structural_input_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                ALLOCATION_POLICY_SHEET: _FakeWorksheet(
                    records=[{AGE_HEADER: "20", ASSET_CLASS_HEADER: "moon_coin", TARGET_WEIGHT_HEADER: "1.0"}]
                )
            }
        )

        with self.assertRaises(StructuralInputError) as ctx:
            _build_allocation_policy(spreadsheet, ASSET_CLASS_REGISTRY)
        self.assertEqual(ctx.exception.field_path, f"{ALLOCATION_POLICY_SHEET}!row2.{ASSET_CLASS_HEADER}")


if __name__ == "__main__":
    unittest.main()
