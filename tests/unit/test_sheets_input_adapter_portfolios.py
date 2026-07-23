import unittest

from adapters.sheets.sheet_mapping import (
    ACCOUNT_ID_HEADER,
    ACCOUNTS_SHEET,
    ASSET_CLASS_HEADER,
    BALANCE_HEADER,
    COST_BASIS_HEADER,
    EXPECTED_RETURN_HEADER,
)
from adapters.sheets.sheets_input_adapter import build_portfolios_from_spreadsheet
from core.domain.value_objects import Money

ASSET_CLASS_REGISTRY = {"cash": "現金", "equity_sp500": "株式（S&P500連動）"}


class _FakeWorksheet:
    def __init__(self, records):
        self._records = records

    def get_all_records(self):
        return self._records


class _FakeSpreadsheet:
    def __init__(self, worksheets: dict):
        self._worksheets = worksheets

    def worksheet(self, name):
        return self._worksheets[name]


def _record(**overrides) -> dict:
    base = {
        ACCOUNT_ID_HEADER: "acc_001",
        BALANCE_HEADER: "5000000",
        ASSET_CLASS_HEADER: "cash",
        EXPECTED_RETURN_HEADER: "0.0",
    }
    base.update(overrides)
    return base


class BuildPortfoliosCostBasisTest(unittest.TestCase):
    def test_blank_cost_basis_defaults_to_balance(self) -> None:
        spreadsheet = _FakeSpreadsheet({ACCOUNTS_SHEET: _FakeWorksheet(records=[_record()])})

        portfolios = build_portfolios_from_spreadsheet(spreadsheet, ASSET_CLASS_REGISTRY)

        holding = portfolios["acc_001"].holdings[0]
        self.assertEqual(holding.current_value, Money.of(5_000_000))
        self.assertEqual(holding.cost_basis, Money.of(5_000_000))

    def test_explicit_cost_basis_is_used_when_different_from_balance(self) -> None:
        spreadsheet = _FakeSpreadsheet(
            {ACCOUNTS_SHEET: _FakeWorksheet(records=[_record(**{COST_BASIS_HEADER: "3000000"})])}
        )

        portfolios = build_portfolios_from_spreadsheet(spreadsheet, ASSET_CLASS_REGISTRY)

        holding = portfolios["acc_001"].holdings[0]
        self.assertEqual(holding.current_value, Money.of(5_000_000))
        self.assertEqual(holding.cost_basis, Money.of(3_000_000))


if __name__ == "__main__":
    unittest.main()
