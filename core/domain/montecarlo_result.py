from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.value_objects import Money


@dataclass
class PercentileBand:
    p5: Money
    p10: Money
    p20: Money
    p30: Money
    p50: Money
    p70: Money
    p80: Money
    p90: Money
    p95: Money


@dataclass
class MonteCarloResult:
    trials: int
    success_count: int
    success_rate: float
    percentile_networth_by_year: dict[int, PercentileBand] = field(default_factory=dict)
