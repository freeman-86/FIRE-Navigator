import unittest
from datetime import date

from adapters.sheets.sheets_input_adapter import (
    _build_accounts,
    _build_event_condition,
    _build_incomes,
    _build_user,
)
from adapters.sheets.sheet_mapping import (
    ACCOUNT_ID_HEADER,
    ACCOUNT_TYPE_HEADER,
    ACCOUNTS_SHEET,
    AGE_CONDITION_LABEL,
    AMOUNT_ANNUAL_HEADER,
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    BIRTH_DATE_HEADER,
    DATE_CONDITION_LABEL,
    EXPECTED_RETURN_HEADER,
    GROWTH_RATE_HEADER,
    INCOME_ID_HEADER,
    INCOMES_SHEET,
    MONTHLY_CONTRIBUTION_HEADER,
    PLAN_SHEET,
    PLAN_START_CONDITION_LABEL,
    SOURCE_HEADER,
    START_TYPE_HEADER,
    START_VALUE_HEADER,
    END_TYPE_HEADER,
    END_VALUE_HEADER,
)
from core.domain.errors import StructuralInputError
from core.domain.value_objects import EventCondition, Money, Rate


class _FakeWorksheet:
    def __init__(self, records=None, values=None):
        self._records = records or []
        self._values = values or []

    def get_all_records(self):
        return self._records

    def get_all_values(self):
        return self._values


class _FakeSpreadsheet:
    def __init__(self, worksheets: dict):
        self._worksheets = worksheets

    def worksheet(self, name):
        return self._worksheets[name]


class BuildUserErrorTest(unittest.TestCase):
    def test_missing_birth_date_raises_structural_input_error_with_field_path(self) -> None:
        settings = {}
        with self.assertRaises(StructuralInputError) as ctx:
            _build_user(settings)
        self.assertEqual(ctx.exception.field_path, f"{PLAN_SHEET}!{BIRTH_DATE_HEADER}")

    def test_malformed_birth_date_raises_structural_input_error(self) -> None:
        settings = {BIRTH_DATE_HEADER: "1990/04/01"}
        with self.assertRaises(StructuralInputError):
            _build_user(settings)


class BuildAccountsErrorTest(unittest.TestCase):
    def test_invalid_account_type_raises_error_with_row_field_path(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                ACCOUNTS_SHEET: _FakeWorksheet(
                    records=[
                        {
                            ACCOUNT_ID_HEADER: "acc_001",
                            ACCOUNT_TYPE_HEADER: "not_a_real_type",
                            BALANCE_HEADER: "1000000",
                            ASSET_CLASS_HEADER: "cash",
                            EXPECTED_RETURN_HEADER: "0.01",
                            MONTHLY_CONTRIBUTION_HEADER: "",
                        }
                    ]
                )
            }
        )
        with self.assertRaises(StructuralInputError) as ctx:
            _build_accounts(spreadsheet)
        self.assertEqual(ctx.exception.field_path, f"{ACCOUNTS_SHEET}!row2.{ACCOUNT_TYPE_HEADER}")

    def test_missing_account_id_raises_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {ACCOUNTS_SHEET: _FakeWorksheet(records=[{ACCOUNT_TYPE_HEADER: "cash"}])}
        )
        with self.assertRaises(StructuralInputError) as ctx:
            _build_accounts(spreadsheet)
        self.assertEqual(ctx.exception.field_path, f"{ACCOUNTS_SHEET}!row2.{ACCOUNT_ID_HEADER}")


class BuildIncomesErrorTest(unittest.TestCase):
    def test_non_numeric_amount_raises_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "not_a_number",
                            GROWTH_RATE_HEADER: "0.01",
                            START_TYPE_HEADER: PLAN_START_CONDITION_LABEL,
                            START_VALUE_HEADER: "",
                            END_TYPE_HEADER: "",
                            END_VALUE_HEADER: "",
                        }
                    ]
                )
            }
        )
        with self.assertRaises(StructuralInputError) as ctx:
            _build_incomes(spreadsheet, Rate.zero())
        self.assertEqual(ctx.exception.field_path, f"{INCOMES_SHEET}!row2.{AMOUNT_ANNUAL_HEADER}")

    def test_missing_start_type_raises_error(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "1000000",
                            GROWTH_RATE_HEADER: "0.01",
                            START_TYPE_HEADER: "",
                            START_VALUE_HEADER: "",
                        }
                    ]
                )
            }
        )
        with self.assertRaises(StructuralInputError):
            _build_incomes(spreadsheet, Rate.zero())


class BuildIncomesGrowthRateDefaultTest(unittest.TestCase):
    def test_blank_growth_rate_defaults_to_inflation_rate(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "1000000",
                            GROWTH_RATE_HEADER: "",
                            START_TYPE_HEADER: PLAN_START_CONDITION_LABEL,
                            START_VALUE_HEADER: "",
                        }
                    ]
                )
            }
        )

        incomes = _build_incomes(spreadsheet, Rate.of("0.02"))

        self.assertEqual(incomes[0].growth_rate, Rate.of("0.02"))

    def test_explicit_growth_rate_takes_priority_over_inflation_rate(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "1000000",
                            GROWTH_RATE_HEADER: "0.01",
                            START_TYPE_HEADER: PLAN_START_CONDITION_LABEL,
                            START_VALUE_HEADER: "",
                        }
                    ]
                )
            }
        )

        incomes = _build_incomes(spreadsheet, Rate.of("0.02"))

        self.assertEqual(incomes[0].growth_rate, Rate.of("0.01"))

    def test_blank_amount_defaults_to_zero_instead_of_raising(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {
                INCOMES_SHEET: _FakeWorksheet(
                    records=[
                        {
                            INCOME_ID_HEADER: "income_001",
                            SOURCE_HEADER: "salary",
                            AMOUNT_ANNUAL_HEADER: "",
                            GROWTH_RATE_HEADER: "0.01",
                            START_TYPE_HEADER: PLAN_START_CONDITION_LABEL,
                            START_VALUE_HEADER: "",
                        }
                    ]
                )
            }
        )

        incomes = _build_incomes(spreadsheet, Rate.of("0.02"))

        self.assertEqual(incomes[0].amount, Money.zero())


class BuildEventConditionLegacyAliasTest(unittest.TestCase):
    """新しいプルダウンには表示しないが、移行前の英語表記(today/plan_start/age/date)が
    既存スプレッドシートのセルに残っていても、手動で書き換えなくてもそのまま読めることを保証する。
    """

    def test_legacy_today_and_plan_start_both_resolve_to_plan_start(self) -> None:
        self.assertEqual(_build_event_condition("today", "", "path"), EventCondition.plan_start())
        self.assertEqual(_build_event_condition("plan_start", "", "path"), EventCondition.plan_start())

    def test_legacy_age_resolves_to_age_condition(self) -> None:
        self.assertEqual(_build_event_condition("age", "45", "path"), EventCondition.at_age(45))

    def test_legacy_date_resolves_to_date_condition(self) -> None:
        self.assertEqual(
            _build_event_condition("date", "2027-06", "path"),
            EventCondition.at_date(date(2027, 6, 1)),
        )

    def test_legacy_values_are_case_insensitive(self) -> None:
        self.assertEqual(_build_event_condition("AGE", "45", "path"), EventCondition.at_age(45))

    def test_new_japanese_labels_still_work(self) -> None:
        self.assertEqual(_build_event_condition(PLAN_START_CONDITION_LABEL, "", "path"), EventCondition.plan_start())
        self.assertEqual(_build_event_condition(AGE_CONDITION_LABEL, "45", "path"), EventCondition.at_age(45))
        self.assertEqual(
            _build_event_condition(DATE_CONDITION_LABEL, "2027-06", "path"),
            EventCondition.at_date(date(2027, 6, 1)),
        )

    def test_date_value_still_works_when_google_sheets_pads_it_to_a_full_date(self) -> None:
        # Google Sheetsのセル書式によっては"2028-12"と入力しても自動的に日付型と解釈され、
        # "2028-12-26"のように日が補完されて保存されることがある。日は元々使われないため、
        # 補完された日付が入っていても寛容に受け付ける。
        self.assertEqual(
            _build_event_condition(DATE_CONDITION_LABEL, "2028-12-26", "path"),
            EventCondition.at_date(date(2028, 12, 1)),
        )


if __name__ == "__main__":
    unittest.main()
