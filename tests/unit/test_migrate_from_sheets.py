import unittest
from datetime import date
from pathlib import Path

from core.domain.account import AccountType
from core.domain.pension import ClaimTiming, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.domain.contribution_strategy import ContributionStrategy
from scripts.migrate_from_sheets import migrate

_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "migrate_from_sheets.py"

# gspreadの書き込み系メソッド名。1つでもこのスクリプトのソースに出てきたら、
# 「スプレッドシートには一切書き込まない」という設計上の制約が破られている可能性がある。
_FORBIDDEN_WRITE_CALLS = (
    ".update(",
    ".update_acell(",
    ".update_title(",
    ".batch_update(",
    ".clear(",
    ".append_row(",
    ".insert_row(",
    ".delete_rows(",
    ".add_worksheet(",
    ".del_worksheet(",
)


def _minimal_plan() -> Plan:
    return Plan(
        plan_id="plan_001",
        name="テストプラン",
        user=User(birth_date=date(1990, 4, 1)),
        start_condition=StartCondition(StartConditionType.TODAY),
        assumptions=Assumptions(inflation_rate=Rate.of("0.02")),
        accounts=[],
        tax_config=TaxConfig(),
        pension=Pension(
            national_pension=PensionEntitlement(estimate_annual=Money.zero()),
            employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
            claim_timing=ClaimTiming(age=65),
        ),
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
        contribution_strategy=ContributionStrategy(order=[AccountType.CASH]),
    )


class MigrateTest(unittest.TestCase):
    def test_produces_the_same_shape_as_plan_serializer(self) -> None:
        plan = _minimal_plan()

        data = migrate(plan, {}, Money.of(20_000_000))

        self.assertEqual(data["plan_id"], "plan_001")
        self.assertEqual(data["target_ending_networth"], 20000000)
        self.assertIn("accounts", data)
        self.assertIn("incomes", data)
        self.assertIn("expenses", data)


class ReadOnlyAgainstSheetsTest(unittest.TestCase):
    """スプレッドシートへは一切書き込まない、という設計上の制約の回帰テスト。

    scripts/migrate_from_sheets.pyのソースを直接検査し、gspreadの書き込み系メソッド呼び出しが
    存在しないこと、およびsheets_input_adapterから読み取り専用の公開関数（load_plan/
    load_portfolios/load_target_ending_networth）以外をimportしていないことを確認する。
    """

    def setUp(self) -> None:
        self.source = _SCRIPT_PATH.read_text(encoding="utf-8")

    def test_source_contains_no_gspread_write_method_calls(self) -> None:
        for forbidden in _FORBIDDEN_WRITE_CALLS:
            self.assertNotIn(
                forbidden, self.source, f"migrate_from_sheets.pyに書き込み系メソッド呼び出しが見つかりました: {forbidden}"
            )

    def test_only_imports_read_only_functions_from_sheets_input_adapter(self) -> None:
        self.assertIn(
            "from adapters.sheets.sheets_input_adapter import load_plan, load_portfolios, load_target_ending_networth",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
