from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.domain.value_objects import EventCondition, Money, Rate


@dataclass
class Income:
    income_id: str
    source: str
    amount: Money
    growth_rate: Rate
    start_condition: EventCondition
    end_condition: Optional[EventCondition] = None
