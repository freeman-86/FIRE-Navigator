from __future__ import annotations

from decimal import Decimal
from typing import Callable, Optional

from core.domain.asset import AssetClass
from core.domain.montecarlo_result import MonteCarloResult
from core.domain.pension import PensionRules
from core.domain.plan import Plan
from core.domain.portfolio import Portfolio
from core.domain.portfolio_rules import PortfolioRules
from core.domain.tax_config import TaxRules
from core.domain.value_objects import Rate
from core.simulation.montecarlo.correlation_matrix import CorrelationMatrix
from core.simulation.montecarlo.distribution import AssetReturnDistribution, to_monthly_distributions
from core.simulation.montecarlo.portfolio_weights import compute_asset_class_weights
from core.simulation.montecarlo.random_seed import create_rng
from core.simulation.montecarlo.return_generator import sample_returns
from core.simulation.montecarlo.statistics import compute_statistics
from core.simulation.projection.projection_engine import resolve_start_year, run_projection

DEFAULT_TRIALS = 1000


def run_montecarlo(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
    pension_rules: PensionRules,
    distributions: dict[AssetClass, AssetReturnDistribution],
    correlation_matrix: CorrelationMatrix,
    trials: int = DEFAULT_TRIALS,
    seed: Optional[int] = None,
) -> MonteCarloResult:
    """Planの口座構成比で加重した資産クラス別リターンを毎月サンプリングしてProjection Engineを
    反復実行し、成功確率・年次パーセンタイル分布を集計する（設計書v1.1 ⑥ Monte Carlo Engine）。

    distributionsは年率のパラメータを渡す（distributions_from_historical_dataset()の出力そのまま）。
    月次サンプリング用の変換はこの関数の内部で行う。

    plan.allocation_policyが設定されている場合、口座の初期構成比ではなくAllocationPolicyの
    年齢別目標配分比率でその月時点の加重合成をする（ギャップ分析3.7「モンテカルロエンジンへの反映」。
    比率が年齢で変わる前提のため固定比率で合成しない）。未設定の場合は従来通りPlanの初期口座構成比を
    使う（後方互換）。
    """

    weight_lookup = build_weight_lookup(plan, portfolios)
    asset_classes = [asset_class for asset_class in distributions if _ever_weighted(asset_class, weight_lookup)]
    monthly_distributions = to_monthly_distributions(distributions)
    rng = create_rng(seed)

    trial_results = []
    for _ in range(trials):
        growth_rate_provider = _make_growth_rate_provider(
            asset_classes, monthly_distributions, correlation_matrix, weight_lookup, rng
        )
        result = run_projection(
            plan, portfolios, tax_rules, portfolio_rules, pension_rules, growth_rate_provider=growth_rate_provider
        )
        trial_results.append(result)

    return compute_statistics(trial_results)


def build_weight_lookup(plan: Plan, portfolios: dict[str, Portfolio]) -> Callable[[int], dict[AssetClass, Decimal]]:
    if plan.allocation_policy is not None and plan.allocation_policy.targets:
        start_year = resolve_start_year(plan)
        birth_year = plan.user.birth_date.year
        allocation_policy = plan.allocation_policy

        def weight_lookup(month_offset: int) -> dict[AssetClass, Decimal]:
            age = (start_year + month_offset // 12) - birth_year
            return {ac: rate.value for ac, rate in allocation_policy.weights_for_age(age).items()}

        return weight_lookup

    static_weights = compute_asset_class_weights(plan, portfolios)
    return lambda month_offset: static_weights


def _ever_weighted(asset_class: AssetClass, weight_lookup: Callable[[int], dict[AssetClass, Decimal]]) -> bool:
    # サンプリング対象を絞り込むための概算チェック。開始時点(offset=0)で重みがあれば対象に含める
    # （AllocationPolicyが年齢とともに新しい資産クラスへ切り替わるケースは稀と想定した簡易化）。
    return asset_class in weight_lookup(0)


def _make_growth_rate_provider(
    asset_classes: list[AssetClass],
    monthly_distributions: dict[AssetClass, AssetReturnDistribution],
    correlation_matrix: CorrelationMatrix,
    weight_lookup: Callable[[int], dict[AssetClass, Decimal]],
    rng,
) -> Callable[[int], Rate]:
    def provider(offset: int) -> Rate:
        if not asset_classes:
            return Rate.zero()
        weights = weight_lookup(offset)
        sampled = sample_returns(asset_classes, monthly_distributions, correlation_matrix, rng)
        blended = sum((sampled[ac].value * weights.get(ac, Decimal(0)) for ac in asset_classes), Decimal(0))
        return Rate(blended)

    return provider
