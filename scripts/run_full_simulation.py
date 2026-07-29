"""スプレッドシート（またはローカルのdata/plan.json）を読み込み→シミュレーション実行→結果を
書き戻す、を一括で行う実行スクリプト。

使い方:
    PYTHONPATH=. python3 scripts/run_full_simulation.py                    # Google Sheetsモード（既定）
    PYTHONPATH=. python3 scripts/run_full_simulation.py --mode local       # data/plan.jsonを使うローカルモード
    PYTHONPATH=. python3 scripts/run_full_simulation.py --quick            # モンテカルロ/ヒストリカルを省略して高速実行
    PYTHONPATH=. python3 scripts/run_full_simulation.py --trials 1000      # モンテカルロの試行回数を指定

普段の利用（フォームからの実行）はweb/app.pyのPOST /api/runが同じcore.services.pipeline_service
を使って行う。このCLIはSheetsモードでの従来通りの一括実行、およびlocalモードでの
ターミナルからのデバッグ実行用に残している。

PYTHONPATHを付けなくても動くよう、リポジトリルートをsys.pathへ自動追加している。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CREDENTIALS_PATH = REPO_ROOT / "secrets" / "gsheets_credentials.json"
DEFAULT_LOCAL_PLAN_PATH = REPO_ROOT / "data" / "plan.json"
DEFAULT_LOCAL_RESULT_PATH = REPO_ROOT / "data" / "result.json"


def main() -> None:
    args = _parse_args()

    print("=" * 60)
    print("FIRE Navigator: フルシミュレーション実行")
    print("=" * 60)

    completed = _run_sheets_mode(args) if args.mode == "sheets" else _run_local_mode(args)

    if not completed:
        sys.exit(1)


def _step(message: str) -> None:
    print(f"\n→ {message}")


def _run_sheets_mode(args: argparse.Namespace) -> bool:
    from adapters.sheets.sheets_error_writer import write_errors
    from adapters.sheets.sheets_input_adapter import build_client, open_spreadsheet
    from core.domain.errors import FireNavigatorError

    if not args.credentials.exists():
        print(f"\n[エラー] 認証キーファイルが見つかりません: {args.credentials}")
        print("README.md の「セットアップ」手順に従って、GCPサービスアカウントの認証キー(JSON)を")
        print(f"{args.credentials} として保存してください。")
        return False

    _step(f"スプレッドシート「{args.spreadsheet_name}」に接続しています...")
    try:
        client = build_client(str(args.credentials))
        spreadsheet = open_spreadsheet(client, args.spreadsheet_name)
    except Exception as e:  # noqa: BLE001 - 接続失敗はユーザーにそのまま伝える
        print(f"\n[エラー] スプレッドシートへの接続に失敗しました: {e}")
        return False
    print(f"      接続完了: {spreadsheet.url}")

    try:
        completed = _run_sheets_pipeline(spreadsheet, args)
    except FireNavigatorError as e:
        print(f"\n[入力エラー] {e.field_path}: {e.message}")
        print("      詳細を出力_エラーシートに書き込みました。入力内容を確認してください。")
        write_errors(spreadsheet, [e])
        completed = False
    except Exception as e:  # noqa: BLE001 - 想定外のエラーもトレースバックではなく分かりやすく表示する
        print(f"\n[予期しないエラー] {type(e).__name__}: {e}")
        if "429" in str(e) or "Quota exceeded" in str(e):
            print("      Google Sheets APIの利用回数制限に達した可能性があります。")
            print("      1分ほど待ってから再実行してください。")
        completed = False

    if not completed:
        # 出力_エラーシートを見ないと気づけず、他の出力シートが前回実行時のまま古くなっている
        # ことに気づきにくいため、ターミナル上でも一目で分かる警告を最後に出す。
        print("\n" + "=" * 60)
        print("⚠️  エラーのため計算は実行されませんでした。出力シートは前回の結果のままです。")
        print("      出力_エラーシートを確認し、入力内容を修正してから再実行してください。")
        print("=" * 60)
        return False

    print("\n" + "=" * 60)
    print("すべての処理が完了しました。")
    print(f"結果はこちらで確認できます: {spreadsheet.url}")
    print("=" * 60)
    return True


def _run_sheets_pipeline(spreadsheet, args: argparse.Namespace) -> bool:
    """スプレッドシートからの読み込み〜core.services.pipeline_serviceでの計算〜書き戻しを行う。

    戻り値は計算が最後まで実行されたかどうか（Falseの場合、出力シートは前回実行時のままで
    更新されていない）。入力の意味的エラーは例外を送出せず、呼び出し元のmain()でterminal上の
    警告を一箇所に集約できるようFalseを返して抜ける。
    """

    from adapters.sheets.sheets_error_writer import write_errors, write_warnings
    from adapters.sheets.sheets_input_adapter import (
        build_plan_from_spreadsheet,
        build_portfolios_from_spreadsheet,
        collect_input_warnings,
        read_target_ending_networth,
    )
    from adapters.sheets.sheets_output_adapter import (
        write_dashboard,
        write_monthly_detail_table,
        write_montecarlo_and_historical_result,
        write_networth_table,
        write_sensitivity_table,
    )
    from core.services.pipeline_service import run_pipeline_for_plan
    from reports.chart_builder import build_networth_chart
    from reports.montecarlo_report_builder import build_percentile_band_chart
    from reports.sensitivity_analysis_builder import build_sensitivity_table

    _step("入力シートを読み込んでいます...")
    plan = build_plan_from_spreadsheet(spreadsheet)
    portfolios = build_portfolios_from_spreadsheet(spreadsheet)
    print(f"      プラン: {plan.name} (口座数: {len(plan.accounts)})")
    target_ending_networth = read_target_ending_networth(spreadsheet)
    input_warnings = collect_input_warnings(spreadsheet)

    outcome = run_pipeline_for_plan(
        plan,
        portfolios,
        target_ending_networth,
        input_warnings=input_warnings,
        trials=args.trials,
        skip_montecarlo=args.quick or args.skip_montecarlo,
        skip_historical=args.quick or args.skip_historical,
        progress=_step,
    )

    if not outcome.succeeded:
        print(f"      [エラー] {len(outcome.semantic_errors)}件の入力矛盾が見つかりました。処理を中断します。")
        write_errors(spreadsheet, outcome.semantic_errors)
        return False
    write_errors(spreadsheet, [])  # 前回実行時のエラー表示をクリア

    if outcome.input_warnings:
        write_warnings(spreadsheet, outcome.input_warnings)
        print(f"      [警告] {len(outcome.input_warnings)}件の入力値が実行時に無視されています（出力_エラーシート参照）")

    result = outcome.result
    write_networth_table(spreadsheet, result, build_networth_chart(plan, result))
    write_monthly_detail_table(spreadsheet, result)
    final_networth = result.yearly_projections[-1].networth if result.yearly_projections else None
    print(f"      完了（計算期間: {len(result.yearly_projections)}年、最終ネットワース: {final_networth}）")
    print(f"      月次詳細（{len(result.monthly_projections)}ヶ月分）を出力_月次詳細シートへ書き込みました")

    write_sensitivity_table(spreadsheet, build_sensitivity_table(outcome.sensitivity_result))
    print(f"      感応度分析完了（資産枯渇年齢: {outcome.dashboard['depletion_age'] or '枯渇なし'}）")

    if outcome.montecarlo_result is not None:
        elapsed = outcome.timings.get("montecarlo", 0.0)
        print(f"      モンテカルロ成功確率: {outcome.montecarlo_result.success_rate:.1%}（所要時間: {elapsed:.1f}秒）")
    if outcome.historical_result is not None:
        elapsed = outcome.timings.get("historical", 0.0)
        print(f"      ヒストリカルバックテスト成功確率: {outcome.historical_result.success_rate:.1%}（所要時間: {elapsed:.1f}秒）")

    montecarlo_entry = (
        (outcome.montecarlo_result, build_percentile_band_chart(outcome.montecarlo_result))
        if outcome.montecarlo_result is not None
        else None
    )
    historical_entry = (
        (outcome.historical_result, build_percentile_band_chart(outcome.historical_result))
        if outcome.historical_result is not None
        else None
    )
    if montecarlo_entry is not None or historical_entry is not None:
        year_to_age = {projection.year: projection.age_self for projection in result.yearly_projections}
        write_montecarlo_and_historical_result(
            spreadsheet, montecarlo_entry, historical_entry, outcome.montecarlo_reference_1971_result, year_to_age
        )

    write_dashboard(
        spreadsheet,
        outcome.dashboard,
        simulation_result=result,
        montecarlo=outcome.montecarlo_result,
        historical=outcome.historical_result,
        montecarlo_reference_1971=outcome.montecarlo_reference_1971_result,
    )
    print("      出力_ダッシュボードへ書き込みました（純資産推移グラフ・資産配分・成功確率を含む）")

    return True


def _run_local_mode(args: argparse.Namespace) -> bool:
    from adapters.local.local_data_adapter import (
        build_plan_from_local_file,
        build_portfolios_from_local_file,
        load_raw,
        read_target_ending_networth,
    )
    from core.domain.errors import FireNavigatorError
    from core.services.pipeline_service import run_pipeline_for_plan
    from reports.output_builder import build_output_json

    if not args.local_plan.exists():
        print(f"\n[エラー] {args.local_plan} が見つかりません。")
        print("        まず scripts/migrate_from_sheets.py 等でdata/plan.jsonを用意してください。")
        return False

    _step(f"{args.local_plan} を読み込んでいます...")
    try:
        data = load_raw(args.local_plan)
        plan = build_plan_from_local_file(data)
        portfolios = build_portfolios_from_local_file(data)
        target_ending_networth = read_target_ending_networth(data)
    except FireNavigatorError as e:
        print(f"\n[入力エラー] {e.field_path}: {e.message}")
        return False
    print(f"      プラン: {plan.name} (口座数: {len(plan.accounts)})")

    outcome = run_pipeline_for_plan(
        plan,
        portfolios,
        target_ending_networth,
        trials=args.trials,
        skip_montecarlo=args.quick or args.skip_montecarlo,
        skip_historical=args.quick or args.skip_historical,
        progress=_step,
    )

    if not outcome.succeeded:
        print(f"\n[エラー] {len(outcome.semantic_errors)}件の入力矛盾が見つかりました。")
        for error in outcome.semantic_errors:
            print(f"      - {error.field_path}: {error.message}")
        return False

    output = build_output_json(outcome)
    args.local_result.parent.mkdir(parents=True, exist_ok=True)
    with open(args.local_result, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print("\n" + "=" * 60)
    print("すべての処理が完了しました。")
    print(f"結果を書き出しました: {args.local_result}")
    print("=" * 60)
    return True


def _parse_args() -> argparse.Namespace:
    from core.services.pipeline_service import DEFAULT_MONTECARLO_TRIALS

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["sheets", "local"], default="sheets", help="入出力先（既定: sheets）")
    parser.add_argument(
        "--spreadsheet-name", default=None, help="スプレッドシート名（--mode sheets。省略時はsheet_mapping.pyの設定値）"
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help="サービスアカウント認証キー(JSON)のパス（--mode sheets）",
    )
    parser.add_argument(
        "--local-plan", type=Path, default=DEFAULT_LOCAL_PLAN_PATH, help="読み込むプランJSONのパス（--mode local）"
    )
    parser.add_argument(
        "--local-result", type=Path, default=DEFAULT_LOCAL_RESULT_PATH, help="結果JSONの書き出し先（--mode local）"
    )
    parser.add_argument("--trials", type=int, default=DEFAULT_MONTECARLO_TRIALS, help="モンテカルロの試行回数")
    parser.add_argument("--skip-montecarlo", action="store_true", help="モンテカルロシミュレーションを省略する")
    parser.add_argument("--skip-historical", action="store_true", help="ヒストリカルバックテストを省略する")
    parser.add_argument("--quick", action="store_true", help="モンテカルロ・ヒストリカルの両方を省略して高速実行する")
    args = parser.parse_args()

    if args.mode == "sheets" and args.spreadsheet_name is None:
        from adapters.sheets.sheet_mapping import SPREADSHEET_NAME

        args.spreadsheet_name = SPREADSHEET_NAME

    return args


if __name__ == "__main__":
    main()
