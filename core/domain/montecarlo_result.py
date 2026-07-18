from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.value_objects import Money


@dataclass
class MonteCarloResult:
    trials: int
    success_rate: float
    percentile_distribution: dict[str, Money] = field(default_factory=dict)
