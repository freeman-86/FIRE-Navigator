"""スプレッドシートを読み込み→シミュレーション実行→結果を書き戻す、を一括で行う実行スクリプト。

使い方:
    PYTHONPATH=. python3 scripts/run_full_simulation.py
    PYTHONPATH=. python3 scripts/run_full_simulation.py --quick          # モンテカルロ/ヒストリカルを省略して高速実行
    PYTHONPATH=. python3 scripts/run_full_simulation.py --trials 1000    # モンテカルロの試行回数を指定

PYTHONPATHを付けなくても動くよう、リポジトリルートをsys.pathへ自動追加している。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CREDENTIALS_PATH = REPO_ROOT / "secrets" / "gsheets_credentials.json"
DEFAULT_MONTECARLO_TRIALS = 1000


def main() -> None:
    args = _parse_args()

    print("=" * 60)
    print("FIRE Navigator: フルシミュレーション実行")
    print("=" * 60)

    from adapters.sheets.sheets_error_writer import write_errors
    from adapters.sheets.sheets_input_adapter import build_client, open_spreadsheet
    from core.domain.errors import FireNavigatorError

    if not args.credentials.exists():
        print(f"\n[エラー] 認証キーファイルが見つかりません: {args.credentials}")
        print("README.md の「セットアップ」手順に従って、GCPサービスアカウントの認証キー(JSON)を")
        print(f"{args.credentials} として保存してください。")
        sys.exit(1)

    print(f"\n[1/9] スプレッドシート「{args.spreadsheet_name}」に接続しています...")
    try:
        client = build_client(str(args.credentials))
        spreadsheet = open_spreadsheet(client, args.spreadsheet_name)
    except Exception as e:  # noqa: BLE001 - 接続失敗はユーザーにそのまま伝える
        print(f"\n[エラー] スプレッドシートへの接続に失敗しました: {e}")
        sys.exit(1)
    print(f"      接続完了: {spreadsheet.url}")

    try:
        _run_pipeline(spreadsheet, args)
    except FireNavigatorError as e:
        print(f"\n[入力エラー] {e.field_path}: {e.message}")
        print("      詳細を出力_エラーシートに書き込みました。入力内容を確認してください。")
        write_errors(spreadsheet, [e])
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - 想定外のエラーもトレースバックではなく分かりやすく表示する
        print(f"\n[予期しないエラー] {type(e).__name__}: {e}")
        if "429" in str(e) or "Quota exceeded" in str(e):
            print("      Google Sheets APIの利用回数制限に達した可能性があります。")
            print("      1分ほど待ってから再実行してください。")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("すべての処理が完了しました。")
    print(f"結果はこちらで確認できます: {spreadsheet.url}")
    print("=" * 60)


def _run_pipeline(spreadsheet, args: argparse.Namespace) -> None:
    from adapters.sheets.sheets_error_writer import write_errors, write_warnings
    from adapters.sheets.sheets_input_adapter import (
        build_plan_from_spreadsheet,
        build_portfolios_from_spreadsheet,
        build_progress_records_from_spreadsheet,
        build_scenarios_from_spreadsheet,
        collect_input_warnings,
        read_target_ending_networth,
    )
    from adapters.sheets.sheets_output_adapter import (
        write_dashboard,
        write_monthly_detail_table,
        write_montecarlo_and_historical_result,
        write_networth_table,
        write_progress_comparison,
        write_scenario_comparison,
        write_sensitivity_table,
    )
    from core.domain.scenario import apply_scenario
    from core.services.validation_service import validate_plan
    from core.simulation.montecarlo.correlation_matrix import compute_correlation_matrix
    from core.simulation.montecarlo.distribution import distributions_from_historical_dataset
    from core.simulation.montecarlo.montecarlo_engine import run_montecarlo
    from core.simulation.historical.historical_engine import run_historical_backtest
    from core.simulation.projection.projection_engine import run_projection
    from core.simulation.projection.sensitivity_analysis import run_sensitivity_analysis
    from reports.chart_builder import build_networth_chart
    from reports.dashboard_builder import build_dashboard
    from reports.montecarlo_report_builder import build_percentile_band_chart
    from reports.progress_comparison_builder import build_progress_comparison_chart
    from reports.scenario_comparison_builder import build_scenario_comparison_chart
    from reports.sensitivity_analysis_builder import build_sensitivity_table
    from repositories.config_repository import load_pension_rules, load_portfolio_rules, load_tax_rules
    from repositories.market_data_repository import load_historical_dataset

    print("\n[2/9] 入力シートを読み込んでいます...")
    plan = build_plan_from_spreadsheet(spreadsheet)
    portfolios = build_portfolios_from_spreadsheet(spreadsheet)
    print(f"      プラン: {plan.name} (口座数: {len(plan.accounts)})")

    tax_rules = load_tax_rules()
    portfolio_rules = load_portfolio_rules()
    pension_rules = load_pension_rules()

    print("\n[3/9] 入力内容を検証しています...")
    semantic_errors = validate_plan(plan, pension_rules)
    if semantic_errors:
        print(f"      [エラー] {len(semantic_errors)}件の入力矛盾が見つかりました。処理を中断します。")
        write_errors(spreadsheet, semantic_errors)
        sys.exit(1)
    write_errors(spreadsheet, [])  # 前回実行時のエラー表示をクリア
    print("      検証OK")

    input_warnings = collect_input_warnings(spreadsheet)
    if input_warnings:
        write_warnings(spreadsheet, input_warnings)
        print(f"      [警告] {len(input_warnings)}件の入力値が実行時に無視されています（出力_エラーシート参照）")

    print("\n[4/9] 基本シミュレーション（決定論的）を実行しています...")
    result = run_projection(plan, portfolios, tax_rules, portfolio_rules, pension_rules)
    write_networth_table(spreadsheet, result, build_networth_chart(plan, result))
    write_monthly_detail_table(spreadsheet, result)
    final_networth = result.yearly_projections[-1].networth if result.yearly_projections else None
    print(f"      完了（計算期間: {len(result.yearly_projections)}年、最終ネットワース: {final_networth}）")
    print(f"      月次詳細（{len(result.monthly_projections)}ヶ月分）を出力_月次詳細シートへ書き込みました")

    print("\n[5/9] ダッシュボード（今月使える金額の逆算等）を計算しています...")
    target_ending_networth = read_target_ending_networth(spreadsheet)
    dashboard = build_dashboard(plan, portfolios, tax_rules, portfolio_rules, pension_rules, target_ending_networth)
    write_dashboard(spreadsheet, dashboard)
    print(f"      完了（資産枯渇年齢: {dashboard['depletion_age'] or '枯渇なし'}）")

    print("\n[6/9] シナリオ比較を実行しています...")
    scenarios = build_scenarios_from_spreadsheet(spreadsheet, plan.plan_id)
    if scenarios:
        results_by_scenario_name = {}
        for scenario in scenarios:
            scenario_plan = apply_scenario(plan, scenario)
            results_by_scenario_name[scenario.name] = run_projection(
                scenario_plan, portfolios, tax_rules, portfolio_rules, pension_rules
            )
        write_scenario_comparison(spreadsheet, build_scenario_comparison_chart(results_by_scenario_name))
        print(f"      完了（{len(scenarios)}シナリオを比較）")
    else:
        print("      入力_シナリオが未設定のためスキップしました")

    print("\n[7/9] 感応度分析を実行しています...")
    sensitivity_result = run_sensitivity_analysis(plan, portfolios, tax_rules, portfolio_rules, pension_rules)
    write_sensitivity_table(spreadsheet, build_sensitivity_table(sensitivity_result))
    print("      完了")

    montecarlo_entry = None
    historical_entry = None

    if args.quick or args.skip_montecarlo:
        print("\n[8/9] モンテカルロシミュレーションをスキップしました（--quick/--skip-montecarlo）")
    else:
        print(f"\n[8/9] モンテカルロシミュレーションを実行しています（試行回数: {args.trials}）...")
        print("      ※ 試行回数が多いほど時間がかかります（数十秒〜数分程度）")
        dataset = load_historical_dataset()
        distributions = distributions_from_historical_dataset(dataset)
        correlation_matrix = compute_correlation_matrix(dataset)
        started = time.time()
        montecarlo_result = run_montecarlo(
            plan, portfolios, tax_rules, portfolio_rules, pension_rules,
            distributions, correlation_matrix, trials=args.trials,
        )
        montecarlo_entry = (montecarlo_result, build_percentile_band_chart(montecarlo_result))
        elapsed = time.time() - started
        print(f"      完了（成功確率: {montecarlo_result.success_rate:.1%}、所要時間: {elapsed:.1f}秒）")

    if args.quick or args.skip_historical:
        print("\n[9/9] ヒストリカルバックテストをスキップしました（--quick/--skip-historical）")
    else:
        print("\n[9/9] ヒストリカルバックテスト（過去の実績データ再生）を実行しています...")
        dataset = load_historical_dataset()
        started = time.time()
        historical_result, _ = run_historical_backtest(plan, portfolios, tax_rules, portfolio_rules, pension_rules, dataset)
        historical_entry = (historical_result, build_percentile_band_chart(historical_result))
        elapsed = time.time() - started
        print(f"      完了（成功確率: {historical_result.success_rate:.1%}、所要時間: {elapsed:.1f}秒）")

    if montecarlo_entry is not None or historical_entry is not None:
        write_montecarlo_and_historical_result(spreadsheet, montecarlo_entry, historical_entry)

    print("\n[実績比較] 入力_実績を確認しています...")
    progress_records = build_progress_records_from_spreadsheet(spreadsheet)
    if progress_records:
        write_progress_comparison(spreadsheet, build_progress_comparison_chart(result, progress_records))
        print(f"      完了（{len(progress_records)}件の実績データと比較）")
    else:
        print("      入力_実績が未設定のためスキップしました")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spreadsheet-name", default=None, help="スプレッドシート名（省略時はsheet_mapping.pyの設定値）")
    parser.add_argument(
        "--credentials", type=Path, default=DEFAULT_CREDENTIALS_PATH, help="サービスアカウント認証キー(JSON)のパス"
    )
    parser.add_argument("--trials", type=int, default=DEFAULT_MONTECARLO_TRIALS, help="モンテカルロの試行回数")
    parser.add_argument("--skip-montecarlo", action="store_true", help="モンテカルロシミュレーションを省略する")
    parser.add_argument("--skip-historical", action="store_true", help="ヒストリカルバックテストを省略する")
    parser.add_argument("--quick", action="store_true", help="モンテカルロ・ヒストリカルの両方を省略して高速実行する")
    args = parser.parse_args()

    if args.spreadsheet_name is None:
        from adapters.sheets.sheet_mapping import SPREADSHEET_NAME

        args.spreadsheet_name = SPREADSHEET_NAME

    return args


if __name__ == "__main__":
    main()
