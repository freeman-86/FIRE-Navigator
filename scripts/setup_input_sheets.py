"""入力シートの入力しやすさを整えるセットアップスクリプト。

以下を一括で設定する（入力シートの既存の値は一切変更しない）:
  - 必須セルへの背景色（薄い黄色）
  - 選択肢が決まっている列へのプルダウン（データの入力規則）
  - 「入力例」シートへの記入例の書き出し
  - タブの並び順・色分け（使用頻度別にグルーピング）

初回セットアップ時や、入力シートの列構成を変更した後に実行する。毎回のシミュレーション実行
（run_full_simulation.py）では自動実行しない（書式設定はAPI呼び出しを消費するため、
値が変わるたびに再実行する必要はない）。

使い方:
    PYTHONPATH=. python3 scripts/setup_input_sheets.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CREDENTIALS_PATH = REPO_ROOT / "secrets" / "gsheets_credentials.json"


def main() -> None:
    args = _parse_args()

    from adapters.sheets.sheets_formatting import apply_input_formatting, organize_sheet_tabs, write_examples_sheet
    from adapters.sheets.sheets_input_adapter import build_client, open_spreadsheet

    if not args.credentials.exists():
        print(f"[エラー] 認証キーファイルが見つかりません: {args.credentials}")
        sys.exit(1)

    print(f"スプレッドシート「{args.spreadsheet_name}」に接続しています...")
    client = build_client(str(args.credentials))
    spreadsheet = open_spreadsheet(client, args.spreadsheet_name)
    print(f"接続完了: {spreadsheet.url}")

    print("必須セルの色分け・プルダウンを設定しています...")
    apply_input_formatting(spreadsheet)
    print("完了しました")

    print("「入力例」シートを書き出しています...")
    write_examples_sheet(spreadsheet)
    print("完了しました")

    print("タブの並び順・色分けを整理しています...")
    organize_sheet_tabs(spreadsheet)
    print("完了しました")

    print(f"\nすべての設定が完了しました: {spreadsheet.url}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spreadsheet-name", default=None, help="スプレッドシート名（省略時はsheet_mapping.pyの設定値）")
    parser.add_argument(
        "--credentials", type=Path, default=DEFAULT_CREDENTIALS_PATH, help="サービスアカウント認証キー(JSON)のパス"
    )
    args = parser.parse_args()

    if args.spreadsheet_name is None:
        from adapters.sheets.sheet_mapping import SPREADSHEET_NAME

        args.spreadsheet_name = SPREADSHEET_NAME

    return args


if __name__ == "__main__":
    main()
