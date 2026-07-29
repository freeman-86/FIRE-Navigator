"""入力アダプタ（Sheets/local）に依存しない、シミュレーションのコア実行フロー。

scripts/run_full_simulation.py（CLI、Sheets/localいずれの入出力にも対応）とweb/app.py
（ローカルWeb UI）の両方が、入力読み込み後〜結果整形までの同じ処理をここから呼ぶ。
結果の書き戻し（Sheetsへの書き込み・JSONファイルへの保存・HTTPレスポンスの組み立て等）は
呼び出し元の責務とし、ここでは一切行わない（core/services/validation_service.pyと同じ
「domain層のオブジェクトだけを受け取り、domain層のオブジェクトだけを返す」設計）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional

from core.domain.errors import FireNavigatorError
from core.domain.market_data import filter_from_year
from core.domain.montecarlo_result import MonteCarloResult
from core.domain.plan import Plan
from core.domain.portfolio import Portfolio
from core.domain.simulation_result import SimulationResult
from core.domain.value_objects import AgeAt, Money
from core.services.validation_service import validate_plan
from core.simulation.historical.historical_engine import run_historical_backtest
from core.simulation.montecarlo.correlation_matrix import compute_correlation_matrix
from core.simulation.montecarlo.distribution import distributions_from_historical_dataset
from core.simulation.montecarlo.montecarlo_engine import run_montecarlo
from core.simulation.projection.projection_engine import run_projection
from core.simulation.projection.sensitivity_analysis import SensitivityResult, run_sensitivity_analysis
from reports.dashboard_builder import build_dashboard
from repositories.config_repository import load_pension_rules, load_portfolio_rules, load_tax_rules
from repositories.market_data_repository import load_historical_dataset

DEFAULT_MONTECARLO_TRIALS = 1000
# 出力側（ダッシュボードの参考値）用: 金本位制終了（ニクソン・ショック）以降のデータだけで
# 分布・相関を推定し直したモンテカルロの基準年。メインのモンテカルロ・ヒストリカルは
# 引き続きconfig/market_data/historical_returns_1928_2024.yamlの全期間データを使う。
GOLD_STANDARD_END_YEAR = 1971


@dataclass
class PipelineOutcome:
    """run_pipeline_for_plan()の結果。

    semantic_errorsが非空の場合、意味的な入力矛盾で処理を打ち切っており、result以降の
    フィールドはすべて未計算（None/デフォルト値）のまま。呼び出し元はsucceededで判定する。
    """

    plan: Plan
    semantic_errors: list[FireNavigatorError] = field(default_factory=list)
    # field_path/messageを持つ警告オブジェクトのリスト。具体的な型は呼び出し元のアダプタに委ねる
    # （例: adapters.sheets.sheets_input_adapter.InputWarning）。ここではそのまま素通しするだけで、
    # core層がadapters層に依存しないよう厳密な型は持たない（設計書3.2 依存方向の原則）。
    input_warnings: list[Any] = field(default_factory=list)
    result: Optional[SimulationResult] = None
    dashboard: Optional[dict] = None
    sensitivity_result: Optional[SensitivityResult] = None
    montecarlo_result: Optional[MonteCarloResult] = None
    montecarlo_reference_1971_result: Optional[MonteCarloResult] = None
    historical_result: Optional[MonteCarloResult] = None
    # フェーズごとの所要時間（秒）。モンテカルロ/ヒストリカルを省略した場合はキーごと存在しない。
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return not self.semantic_errors


def run_pipeline_for_plan(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    target_ending_networth: Money,
    *,
    input_warnings: Optional[list[Any]] = None,
    trials: int = DEFAULT_MONTECARLO_TRIALS,
    skip_montecarlo: bool = False,
    skip_historical: bool = False,
    progress: Optional[Callable[[str], None]] = None,
) -> PipelineOutcome:
    """入力読み込み後〜結果整形までの、アダプタ非依存のコア処理。

    plan/portfolios/target_ending_networthはSheets/localいずれのアダプタが読み込んだものでもよい
    （すでにdomain層のオブジェクトへ変換済みである前提）。progressは各フェーズ開始時に日本語の
    短いメッセージを渡すコールバック（CLIでのprint、Web UIでのログ収集等に使う。省略可）。
    """

    def report(message: str) -> None:
        if progress is not None:
            progress(message)

    pension_rules = load_pension_rules()
    tax_rules = load_tax_rules()
    portfolio_rules = load_portfolio_rules()

    report("入力内容を検証しています...")
    semantic_errors = validate_plan(plan, pension_rules)
    if semantic_errors:
        return PipelineOutcome(plan=plan, semantic_errors=semantic_errors, input_warnings=input_warnings or [])

    report("基本シミュレーション（決定論的）を実行しています...")
    result = run_projection(plan, portfolios, tax_rules, portfolio_rules, pension_rules)

    report("ダッシュボード（今月使える金額の逆算等）を計算しています...")
    dashboard = build_dashboard(plan, portfolios, tax_rules, portfolio_rules, pension_rules, target_ending_networth)

    report("感応度分析を実行しています...")
    sensitivity_result = run_sensitivity_analysis(plan, portfolios, tax_rules, portfolio_rules, pension_rules)

    timings: dict[str, float] = {}
    montecarlo_result = None
    montecarlo_reference_1971_result = None
    if not skip_montecarlo:
        report(f"モンテカルロシミュレーションを実行しています（試行回数: {trials}）...")
        dataset = load_historical_dataset()
        distributions = distributions_from_historical_dataset(dataset)
        correlation_matrix = compute_correlation_matrix(dataset)
        started = time.time()
        montecarlo_result = run_montecarlo(
            plan, portfolios, tax_rules, portfolio_rules, pension_rules,
            distributions, correlation_matrix, trials=trials,
        )
        timings["montecarlo"] = time.time() - started

        report(f"モンテカルロ（参考: {GOLD_STANDARD_END_YEAR}年以降のデータで分布推定）を実行しています...")
        dataset_1971 = filter_from_year(dataset, GOLD_STANDARD_END_YEAR)
        distributions_1971 = distributions_from_historical_dataset(dataset_1971)
        correlation_matrix_1971 = compute_correlation_matrix(dataset_1971)
        started = time.time()
        montecarlo_reference_1971_result = run_montecarlo(
            plan, portfolios, tax_rules, portfolio_rules, pension_rules,
            distributions_1971, correlation_matrix_1971, trials=trials,
        )
        timings["montecarlo_reference_1971"] = time.time() - started

    historical_result = None
    if not skip_historical:
        report("ヒストリカルバックテスト（過去の実績データ再生）を実行しています...")
        dataset = load_historical_dataset()
        # 窓の長さ(何年分バックテストするか)を、想定寿命と現在の年齢から算出する
        # （固定30年ではなく、モンテカルロ等と同様に想定寿命と連動させる）。
        current_age = AgeAt(plan.user.birth_date, date.today()).years
        window_length = max(plan.life_expectancy_age - current_age, 1)
        started = time.time()
        historical_result, _ = run_historical_backtest(
            plan, portfolios, tax_rules, portfolio_rules, pension_rules, dataset, window_length
        )
        timings["historical"] = time.time() - started

    return PipelineOutcome(
        plan=plan,
        semantic_errors=[],
        input_warnings=input_warnings or [],
        result=result,
        dashboard=dashboard,
        sensitivity_result=sensitivity_result,
        montecarlo_result=montecarlo_result,
        montecarlo_reference_1971_result=montecarlo_reference_1971_result,
        historical_result=historical_result,
        timings=timings,
    )
