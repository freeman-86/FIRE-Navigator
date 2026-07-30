"""FIRE Navigatorのローカル完結ダッシュボードを提供するFlaskアプリ。

data/plan.json（adapters/local/local_data_adapter.py）を入出力先とし、外部サービスには
一切依存しない。「シミュレーション実行」ボタン相当のPOST /api/runは、CLI版
（scripts/run_full_simulation.py）と同じcore.services.pipeline_serviceの
run_pipeline_for_plan()を呼ぶため、計算ロジックの重複はない。

使い方:
    PYTHONPATH=. python3 web/app.py
    PYTHONPATH=. python3 web/app.py --port 5050

シミュレーション実行.commandからはこのファイルがバックグラウンドで起動される。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, jsonify, render_template, request  # noqa: E402

from adapters.local.local_data_adapter import (  # noqa: E402
    DEFAULT_PLAN_FILE_PATH,
    build_plan_from_local_file,
    build_portfolios_from_local_file,
    load_raw,
    read_target_ending_networth,
    save_plan,
)
from core.domain.account import AccountType  # noqa: E402
from core.domain.errors import SchemaValidationError  # noqa: E402
from core.services.pipeline_service import DEFAULT_MONTECARLO_TRIALS, run_pipeline_for_plan  # noqa: E402
from reports.output_builder import build_output_json  # noqa: E402
from repositories.asset_class_repository import load_asset_class_registry  # noqa: E402

DEFAULT_PORT = 5001

# data/plan.json がまだ存在しない（初回起動）場合にフォームへ渡す、空のプラン。
# キー構成はlocal_data_adapter.pyが読み込める形と完全に一致させる（フォームがそのまま
# POST /api/plan・/api/runへ送り返せるように）。
EMPTY_PLAN: dict = {
    "schema_version": 1,
    "plan_id": "plan_001",
    "name": "",
    "user": {"birth_date": None},
    "assumptions": {"inflation_rate": None},
    "pension": {
        "national_pension_estimate_annual": None,
        "employee_pension_estimate_annual": None,
        "claim_age": None,
    },
    "life_expectancy_age": None,
    "target_ending_networth": None,
    "accounts": [],
    "incomes": [],
    "expenses": [],
    "allocation_policy": None,
    "children": [],
    "education_expenses": [],
}

app = Flask(__name__)
# Jinja2はデフォルトでテンプレートをコンパイル後キャッシュし、debug=Falseだとファイル変更を
# 検知しない（index.htmlを編集してもサーバー再起動なしには反映されない）。静的ファイル
# （static/配下）は元々リクエストごとにディスクから読むためこの問題はない。
app.config["TEMPLATES_AUTO_RELOAD"] = True
# テストから差し替えられるよう、実データファイルのパスをapp.configに置く（ルート内では
# 必ずこの値を明示的に渡し、各アダプタ関数のデフォルト引数には頼らない。デフォルト引数は
# 関数定義時に評価されるため、テストがモジュール属性を差し替えても効かないため）。
app.config["PLAN_FILE_PATH"] = DEFAULT_PLAN_FILE_PATH


def _validation_error_response(error: SchemaValidationError):
    return jsonify({"errors": [{"field_path": error.field_path, "message": error.message}]}), 422


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/plan", methods=["GET", "POST"])
def api_plan():
    plan_file_path = Path(app.config["PLAN_FILE_PATH"])

    if request.method == "GET":
        if plan_file_path.exists():
            return jsonify(load_raw(plan_file_path))
        return jsonify(EMPTY_PLAN)

    data = request.get_json(force=True, silent=False)
    try:
        save_plan(data, plan_file_path)
    except SchemaValidationError as e:
        return _validation_error_response(e)
    return jsonify({"saved": True})


@app.route("/api/run", methods=["POST"])
def api_run():
    data = request.get_json(force=True, silent=False)

    # 保存前に検証する（保存はplan.jsonへの書き込みを伴うため、壊れた入力で
    # 既存の正常なファイルを上書きしないよう、save_plan自体も内部で同じ検証をもう一度行う）。
    try:
        plan = build_plan_from_local_file(data)
        portfolios = build_portfolios_from_local_file(data)
        target_ending_networth = read_target_ending_networth(data)
    except SchemaValidationError as e:
        return _validation_error_response(e)

    save_plan(data, Path(app.config["PLAN_FILE_PATH"]))

    # モンテカルロ/ヒストリカルは時間がかかる（数十秒〜数分）ため既定では省略し、
    # フォーム側のチェックボックスで明示的に含めた場合だけ実行する
    # （?include_montecarlo=1、POSTボディはプランのJSONのみに保つためクエリ文字列で渡す）。
    include_montecarlo = request.args.get("include_montecarlo") == "1"
    trials = request.args.get("trials", type=int) or DEFAULT_MONTECARLO_TRIALS
    outcome = run_pipeline_for_plan(
        plan,
        portfolios,
        target_ending_networth,
        trials=trials,
        skip_montecarlo=not include_montecarlo,
        skip_historical=not include_montecarlo,
    )

    if not outcome.succeeded:
        return (
            jsonify(
                {
                    "errors": [
                        {"field_path": e.field_path, "message": e.message} for e in outcome.semantic_errors
                    ]
                }
            ),
            422,
        )

    return jsonify(build_output_json(outcome))


@app.route("/api/asset-classes")
def api_asset_classes():
    return jsonify(load_asset_class_registry())


@app.route("/api/account-types")
def api_account_types():
    return jsonify([account_type.value for account_type in AccountType])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"待ち受けポート（既定: {DEFAULT_PORT}）")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
