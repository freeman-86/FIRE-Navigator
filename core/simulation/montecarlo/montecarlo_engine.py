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
from core.simulation.projection.projection_engine import run_projection

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
    """

    asset_class_weights = compute_asset_class_weights(plan, portfolios)
    asset_classes = [asset_class for asset_class in distributions if asset_class in asset_class_weights]
    monthly_distributions = to_monthly_distributions(distributions)
    rng = create_rng(seed)

    trial_results = []
    for _ in range(trials):
        growth_rate_provider = _make_growth_rate_provider(
            asset_classes, monthly_distributions, correlation_matrix, asset_class_weights, rng
        )
        result = run_projection(
            plan, portfolios, tax_rules, portfolio_rules, pension_rules, growth_rate_provider=growth_rate_provider
        )
        trial_results.append(result)

    return compute_statistics(trial_results)


def _make_growth_rate_provider(
    asset_classes: list[AssetClass],
    monthly_distributions: dict[AssetClass, AssetReturnDistribution],
    correlation_matrix: CorrelationMatrix,
    asset_class_weights: dict[AssetClass, Decimal],
    rng,
) -> Callable[[int], Rate]:
    def provider(offset: int) -> Rate:
        if not asset_classes:
            return Rate.zero()
        sampled = sample_returns(asset_classes, monthly_distributions, correlation_matrix, rng)
        blended = sum((sampled[ac].value * asset_class_weights[ac] for ac in asset_classes), Decimal(0))
        return Rate(blended)

    return provider
