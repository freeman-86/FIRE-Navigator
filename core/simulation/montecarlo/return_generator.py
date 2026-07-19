from __future__ import annotations

import math
import random

from core.domain.asset import AssetClass
from core.domain.value_objects import Rate
from core.simulation.montecarlo.correlation_matrix import CorrelationMatrix
from core.simulation.montecarlo.distribution import AssetReturnDistribution


def sample_returns(
    asset_classes: list[AssetClass],
    distributions: dict[AssetClass, AssetReturnDistribution],
    correlation_matrix: CorrelationMatrix,
    rng: random.Random,
) -> dict[AssetClass, Rate]:
    """相関を考慮した多変量正規分布近似で、資産クラスごとのリターンを1期間分サンプリングする。

    distributionsの単位（年率/月率）に応じて、そのまま年次/月次いずれのサンプリングにも使える。
    """

    n = len(asset_classes)
    covariance = [
        [
            float(distributions[a].std_dev.value) * float(distributions[b].std_dev.value) * correlation_matrix.get(a, b)
            for b in asset_classes
        ]
        for a in asset_classes
    ]
    cholesky = _cholesky(covariance)
    independent = [rng.gauss(0.0, 1.0) for _ in range(n)]
    correlated = [sum(cholesky[i][k] * independent[k] for k in range(i + 1)) for i in range(n)]

    return {
        asset_class: Rate.of(float(distributions[asset_class].mean.value) + correlated[i])
        for i, asset_class in enumerate(asset_classes)
    }


def _cholesky(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            total = sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                lower[i][j] = math.sqrt(max(matrix[i][i] - total, 0.0))
            else:
                lower[i][j] = (matrix[i][j] - total) / lower[j][j] if lower[j][j] != 0 else 0.0
    return lower
