"""既存のGoogleスプレッドシートの内容をdata/plan.jsonへ変換する、一回限りの移行スクリプト。

スプレッドシートへの書き込みは一切行わない（読み取り専用）。adapters/sheets/sheets_input_adapter.py
のload_plan/load_portfolios/load_target_ending_networth（生セルを解析済みのPlan/Portfolio/Money
オブジェクトへ変換する、読み取り専用の公開関数）だけを使い、Sheetsの生セルを自前で再解析することは
しない。この関数群がgspreadの書き込み系メソッド（update/batch_update/clear等）を一切呼ばないことは
tests/unit/test_migrate_from_sheets.pyで検証している。

使い方:
    PYTHONPATH=. python3 scripts/migrate_from_sheets.py
    PYTHONPATH=. python3 scripts/migrate_from_sheets.py --output data/plan.json --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CREDENTIALS_PATH = REPO_ROOT / "secrets" / "gsheets_credentials.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "data" / "plan.json"


def migrate(plan, portfolios, target_ending_networth) -> dict:
    """Plan/Portfolio/目標資産（いずれもSheetsアダプタが返す読み取り済みのドメインオブジェクト）を、
    local_data_adapter.pyが読み込めるJSON辞書に変換する。ファイルI/O・argparse等のCLIの都合を
    含まない純粋関数にしておくことで、テストがtempfile/argvなしに直接呼び出せるようにする。
    """

    from adapters.local.plan_serializer import to_json_dict

    return to_json_dict(plan, portfolios, target_ending_networth)


def main() -> None:
    args = _parse_args()

    if not args.credentials.exists():
        print(f"[エラー] 認証キーファイルが見つかりません: {args.credentials}")
        sys.exit(1)

    if args.output.exists() and args.output.stat().st_size > 0 and not args.force:
        print(f"[エラー] 出力先が既に存在します: {args.output}")
        print("        既存のローカルデータを上書きしてよい場合のみ --force を指定してください。")
        sys.exit(1)

    from adapters.local.local_data_adapter import save_plan
    from adapters.sheets.sheets_input_adapter import load_plan, load_portfolios, load_target_ending_networth

    print(f"スプレッドシート「{args.spreadsheet_name}」から読み込んでいます（読み取り専用）...")
    plan = load_plan(args.spreadsheet_name, str(args.credentials))
    portfolios = load_portfolios(args.spreadsheet_name, str(args.credentials))
    target_ending_networth = load_target_ending_networth(args.spreadsheet_name, str(args.credentials))

    data = migrate(plan, portfolios, target_ending_networth)
    save_plan(data, args.output)

    print(f"移行完了: {args.output} に書き出しました。")
    print("（スプレッドシート自体には一切変更を加えていません）")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--spreadsheet-name", default=None, help="スプレッドシート名（省略時はsheet_mapping.pyの設定値）"
    )
    parser.add_argument(
        "--credentials", type=Path, default=DEFAULT_CREDENTIALS_PATH, help="サービスアカウント認証キー(JSON)のパス"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="出力先JSONファイルのパス")
    parser.add_argument("--force", action="store_true", help="出力先が既に存在していても上書きする")
    args = parser.parse_args()

    if args.spreadsheet_name is None:
        from adapters.sheets.sheet_mapping import SPREADSHEET_NAME

        args.spreadsheet_name = SPREADSHEET_NAME

    return args


if __name__ == "__main__":
    main()
