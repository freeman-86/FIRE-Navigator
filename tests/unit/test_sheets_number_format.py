import unittest

from adapters.sheets.sheet_mapping import AGE_HEADER, BALANCE_HEADER, YEAR_HEADER
from adapters.sheets.sheets_number_format import money_column_format_requests, money_row_format_requests


class MoneyColumnFormatRequestsTest(unittest.TestCase):
    def test_formats_columns_not_in_the_non_money_exclusion_set(self) -> None:
        header = [YEAR_HEADER, AGE_HEADER, BALANCE_HEADER, "未知の新しい列"]

        requests = money_column_format_requests(sheet_id=42, header=header, start_row=1, end_row=300)

        formatted_columns = {r["repeatCell"]["range"]["startColumnIndex"] for r in requests}
        self.assertEqual(formatted_columns, {2, 3})  # BALANCE_HEADER、未知の列(将来追加された列)

    def test_skips_blank_header_cells(self) -> None:
        header = [BALANCE_HEADER, ""]

        requests = money_column_format_requests(sheet_id=1, header=header, start_row=1, end_row=10)

        self.assertEqual(len(requests), 1)

    def test_request_range_and_number_format_pattern(self) -> None:
        requests = money_column_format_requests(sheet_id=7, header=[BALANCE_HEADER], start_row=1, end_row=300)

        request = requests[0]["repeatCell"]
        self.assertEqual(
            request["range"],
            {"sheetId": 7, "startRowIndex": 1, "endRowIndex": 300, "startColumnIndex": 0, "endColumnIndex": 1},
        )
        self.assertEqual(request["cell"]["userEnteredFormat"]["numberFormat"], {"type": "NUMBER", "pattern": "#,##0"})
        self.assertEqual(request["fields"], "userEnteredFormat.numberFormat")


class MoneyRowFormatRequestsTest(unittest.TestCase):
    def test_formats_rows_not_in_the_non_money_exclusion_set(self) -> None:
        labels = [BALANCE_HEADER, AGE_HEADER, YEAR_HEADER, "未知の新しいラベル"]

        requests = money_row_format_requests(sheet_id=1, row_labels=labels)

        formatted_rows = {r["repeatCell"]["range"]["startRowIndex"] for r in requests}
        self.assertEqual(formatted_rows, {0, 3})

    def test_targets_the_given_value_column(self) -> None:
        requests = money_row_format_requests(sheet_id=1, row_labels=[BALANCE_HEADER], value_col=1)

        request = requests[0]["repeatCell"]
        self.assertEqual(request["range"]["startColumnIndex"], 1)
        self.assertEqual(request["range"]["endColumnIndex"], 2)


if __name__ == "__main__":
    unittest.main()
