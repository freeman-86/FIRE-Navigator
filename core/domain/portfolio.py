from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.holding import Holding


@dataclass
class Portfolio:
    holdings: list[Holding] = field(default_factory=list)
