"""ローカルのdata/plan.jsonを読み込み→シミュレーション実行→結果をdata/result.jsonへ書き出す、
を一括で行うCLIスクリプト。

使い方:
    PYTHONPATH=. python3 scripts/run_full_simulation.py
    PYTHONPATH=. python3 scripts/run_full_simulation.py --quick            # モンテカルロ/ヒストリカルを省略して高速実行
    PYTHONPATH=. python3 scripts/run_full_simulation.py --trials 1000      # モンテカルロの試行回数を指定

普段の利用（フォームからの実行）はweb/app.pyのPOST /api/runが同じcore.services.pipeline_service
を使って行う。このCLIはターミナルからのデバッグ実行用に残している。

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

DEFAULT_LOCAL_PLAN_PATH = REPO_ROOT / "data" / "plan.json"
DEFAULT_LOCAL_RESULT_PATH = REPO_ROOT / "data" / "result.json"


def main() -> None:
    args = _parse_args()

    print("=" * 60)
    print("FIRE Navigator: フルシミュレーション実行")
    print("=" * 60)

    if not _run(args):
        sys.exit(1)


def _step(message: str) -> None:
    print(f"\n→ {message}")


def _run(args: argparse.Namespace) -> bool:
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
        print("        まずWebフォーム（シミュレーション実行.command）で入力・保存してください。")
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
    parser.add_argument("--local-plan", type=Path, default=DEFAULT_LOCAL_PLAN_PATH, help="読み込むプランJSONのパス")
    parser.add_argument(
        "--local-result", type=Path, default=DEFAULT_LOCAL_RESULT_PATH, help="結果JSONの書き出し先"
    )
    parser.add_argument("--trials", type=int, default=DEFAULT_MONTECARLO_TRIALS, help="モンテカルロの試行回数")
    parser.add_argument("--skip-montecarlo", action="store_true", help="モンテカルロシミュレーションを省略する")
    parser.add_argument("--skip-historical", action="store_true", help="ヒストリカルバックテストを省略する")
    parser.add_argument("--quick", action="store_true", help="モンテカルロ・ヒストリカルの両方を省略して高速実行する")
    return parser.parse_args()


if __name__ == "__main__":
    main()
